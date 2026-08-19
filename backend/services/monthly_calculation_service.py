import calendar
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from backend.models.micro_unit_channel import MicroUnitChannel
from backend.models.post_snapshot import PostSnapshot
from backend.models.monthly_channel_metric import MonthlyChannelMetric

def _get_start_and_end_of_month(year: int, month: int):
    start_date = datetime(year, month, 1)
    _, last_day = calendar.monthrange(year, month)
    end_date = datetime(year, month, last_day, 23, 59, 59)
    return start_date, end_date

def _get_prior_6_months_range(target_month_start: datetime):
    prior_month = target_month_start.month - 6
    prior_year = target_month_start.year
    if prior_month <= 0:
        prior_month += 12
        prior_year -= 1
    six_months_prior = datetime(prior_year, prior_month, 1)
    
    day_before_target = target_month_start - timedelta(days=1)
    day_before_target = day_before_target.replace(hour=23, minute=59, second=59)
    return six_months_prior, day_before_target

async def calculate_monthly_metrics(db: AsyncSession, year: int, month: int, snapshot1_run_id: int, snapshot2_run_id: int) -> dict:
    channels_result = await db.execute(select(MicroUnitChannel))
    channels = channels_result.scalars().all()
    
    target_start, target_end = _get_start_and_end_of_month(year, month)
    prior_start, prior_end = _get_prior_6_months_range(target_start)
    
    channels_processed = 0
    
    for channel in channels:
        # Get S1 posts
        s1_query = select(PostSnapshot).where(
            (PostSnapshot.run_id == snapshot1_run_id) & 
            ((PostSnapshot.owner_username == channel.username) | (PostSnapshot.input_url.contains(channel.username)))
        )
        s1_result = await db.execute(s1_query)
        s1_posts = {p.post_id: p for p in s1_result.scalars().all()}
        
        # Get S2 posts
        s2_query = select(PostSnapshot).where(
            (PostSnapshot.run_id == snapshot2_run_id) & 
            ((PostSnapshot.owner_username == channel.username) | (PostSnapshot.input_url.contains(channel.username)))
        )
        s2_result = await db.execute(s2_query)
        s2_posts = {p.post_id: p for p in s2_result.scalars().all()}
        
        total_delta = 0.0
        post_count = 0
        
        for post_id, s2_p in s2_posts.items():
            if not s2_p.timestamp:
                continue
            
            # check publish date
            pub_date = s2_p.timestamp.replace(tzinfo=None)
            
            coauthors = s2_p.coauthor_producers if s2_p.coauthor_producers else []
            participants = max(1, len(coauthors) + 1)
            
            if prior_start <= pub_date <= prior_end:
                s1_p = s1_posts.get(post_id)
                if s1_p:
                    s2_views = s2_p.video_play_count or 0
                    s1_views = s1_p.video_play_count or 0
                    delta = max(0, (s2_views / participants) - (s1_views / participants))
                    total_delta += delta
            elif target_start <= pub_date <= target_end:
                s2_views = s2_p.video_play_count or 0
                delta = s2_views / participants
                total_delta += delta
                post_count += 1
                
        views_per_post = total_delta / post_count if post_count > 0 else 0.0
        year_month_str = f"{year}-{month:02d}"
        
        # Determine previous_monthly_views for growth
        prev_month = target_start.month - 1
        prev_year = target_start.year
        if prev_month <= 0:
            prev_month += 12
            prev_year -= 1
        prev_year_month_str = f"{prev_year}-{prev_month:02d}"
        
        prev_metric_query = select(MonthlyChannelMetric.monthly_views).where(
            (MonthlyChannelMetric.instagram_id == channel.instagram_id) & 
            (MonthlyChannelMetric.year_month == prev_year_month_str)
        )
        prev_metric_result = await db.execute(prev_metric_query)
        prev_views = prev_metric_result.scalar_one_or_none()
        
        growth_percent = None
        if prev_views and prev_views > 0:
            growth_percent = ((total_delta - prev_views) / prev_views) * 100
        
        # Upsert
        stmt = insert(MonthlyChannelMetric).values(
            instagram_id=channel.instagram_id,
            username=channel.username,
            year_month=year_month_str,
            monthly_views=total_delta,
            previous_monthly_views=prev_views,
            growth_percent=growth_percent,
            post_count=post_count,
            views_per_post=views_per_post,
            snapshot1_run_id=snapshot1_run_id,
            snapshot2_run_id=snapshot2_run_id
        )
        
        do_update_stmt = stmt.on_conflict_do_update(
            constraint="uq_channel_month",
            set_={
                "username": stmt.excluded.username,
                "monthly_views": stmt.excluded.monthly_views,
                "previous_monthly_views": stmt.excluded.previous_monthly_views,
                "growth_percent": stmt.excluded.growth_percent,
                "post_count": stmt.excluded.post_count,
                "views_per_post": stmt.excluded.views_per_post,
                "snapshot1_run_id": stmt.excluded.snapshot1_run_id,
                "snapshot2_run_id": stmt.excluded.snapshot2_run_id,
                "calculated_at": func.now()
            }
        )
        
        await db.execute(do_update_stmt)
        channels_processed += 1
        
    await db.commit()
    return {"channels_processed": channels_processed}
