import calendar
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from backend.models.micro_unit_channel import MicroUnitChannel
from backend.models.post_snapshot import PostSnapshot
from backend.models.monthly_channel_metric import MonthlyChannelMetric
from backend.repositories.analytics_repo import (
    get_wisdom_warriors_monthly_views_filtered,
    WISDOM_WARRIOR_ALLOWED_HASHTAGS,
    WISDOM_WARRIOR_ALLOWED_CAPTION_KEYWORDS,
    WISDOM_WARRIOR_ALLOWED_MENTIONS,
    WISDOM_WARRIOR_ALLOWED_TAGGED_USERS,
)


def _get_prior_6_months(year: int, month: int) -> list[str]:
    prior_months = []
    cur_y, cur_m = year, month
    for _ in range(6):
        cur_m -= 1
        if cur_m <= 0:
            cur_m = 12
            cur_y -= 1
        prior_months.append(f"{cur_y}-{cur_m:02d}")
    return prior_months


async def calculate_monthly_metrics(
    db: AsyncSession,
    year: int,
    month: int,
    snapshot1_run_id: int,
    snapshot2_run_id: int,
) -> dict:
    channels_result = await db.execute(select(MicroUnitChannel))
    channels = channels_result.scalars().all()
    if not channels:
        return {"channels_processed": 0}

    target_year_month = f"{year}-{month:02d}"
    prior_months = _get_prior_6_months(year, month)

    # Dictionary to accumulate total views per normalized username
    # username_key -> total_delta
    channel_totals: dict[str, float] = {
        c.username.strip().lstrip("@").lower(): 0.0 for c in channels
    }

    # 1. Calculate prior 6 months decay delta (S2 - S1)
    for prior_m in prior_months:
        s1_data = await get_wisdom_warriors_monthly_views_filtered(
            db=db,
            month=prior_m,
            apply_filters=True,
            hashtags=WISDOM_WARRIOR_ALLOWED_HASHTAGS,
            mentions=WISDOM_WARRIOR_ALLOWED_MENTIONS,
            tagged_users=WISDOM_WARRIOR_ALLOWED_TAGGED_USERS,
            caption_keywords=WISDOM_WARRIOR_ALLOWED_CAPTION_KEYWORDS,
            category=None,
            snapshot_run_id=snapshot1_run_id,
        )
        s1_views_by_user = {
            item["username"].strip().lstrip("@").lower(): float(item.get("total_views") or 0)
            for item in s1_data
        }

        s2_data = await get_wisdom_warriors_monthly_views_filtered(
            db=db,
            month=prior_m,
            apply_filters=True,
            hashtags=WISDOM_WARRIOR_ALLOWED_HASHTAGS,
            mentions=WISDOM_WARRIOR_ALLOWED_MENTIONS,
            tagged_users=WISDOM_WARRIOR_ALLOWED_TAGGED_USERS,
            caption_keywords=WISDOM_WARRIOR_ALLOWED_CAPTION_KEYWORDS,
            category=None,
            snapshot_run_id=snapshot2_run_id,
        )
        s2_views_by_user = {
            item["username"].strip().lstrip("@").lower(): float(item.get("total_views") or 0)
            for item in s2_data
        }

        for uname in channel_totals:
            s1_v = s1_views_by_user.get(uname, 0.0)
            s2_v = s2_views_by_user.get(uname, 0.0)
            month_delta = max(0.0, s2_v - s1_v)
            channel_totals[uname] += month_delta

    # 2. Add target month views directly from S2 (ignoring S1 for target month posts)
    target_s2_data = await get_wisdom_warriors_monthly_views_filtered(
        db=db,
        month=target_year_month,
        apply_filters=True,
        hashtags=WISDOM_WARRIOR_ALLOWED_HASHTAGS,
        mentions=WISDOM_WARRIOR_ALLOWED_MENTIONS,
        tagged_users=WISDOM_WARRIOR_ALLOWED_TAGGED_USERS,
        caption_keywords=WISDOM_WARRIOR_ALLOWED_CAPTION_KEYWORDS,
        category=None,
        snapshot_run_id=snapshot2_run_id,
    )
    target_views_by_user = {
        item["username"].strip().lstrip("@").lower(): float(item.get("total_views") or 0)
        for item in target_s2_data
    }

    for uname in channel_totals:
        channel_totals[uname] += target_views_by_user.get(uname, 0.0)

    # 3. Determine reels count and static posts count in target month from S2
    s2_target_posts = await db.execute(
        select(PostSnapshot).where(
            (PostSnapshot.run_id == snapshot2_run_id)
            & (PostSnapshot.timestamp.is_not(None))
            & (func.to_char(PostSnapshot.timestamp, "YYYY-MM") == target_year_month)
        )
    )
    all_s2_posts = s2_target_posts.scalars().all()
    post_counts_by_user: dict[str, int] = {uname: 0 for uname in channel_totals}
    reels_counts_by_user: dict[str, int] = {uname: 0 for uname in channel_totals}
    static_counts_by_user: dict[str, int] = {uname: 0 for uname in channel_totals}

    for p in all_s2_posts:
        owner = (p.owner_username or "").strip().lstrip("@").lower()
        inp = (p.input_url or "").lower()

        # Check if reel (video) or static post (image/carousel)
        is_reel = (
            (p.type in ("Video", "ReelVideo"))
            or (p.product_type == "clips")
            or bool(p.video_play_count and p.video_play_count > 0)
            or bool(p.video_view_count and p.video_view_count > 0)
        )

        for uname in channel_totals:
            if uname == owner or uname in inp:
                post_counts_by_user[uname] += 1
                if is_reel:
                    reels_counts_by_user[uname] += 1
                else:
                    static_counts_by_user[uname] += 1

    # 4. Upsert into monthly_channel_metrics
    prev_month_num = month - 1
    prev_year_num = year
    if prev_month_num <= 0:
        prev_month_num = 12
        prev_year_num -= 1
    prev_year_month_str = f"{prev_year_num}-{prev_month_num:02d}"

    channels_processed = 0

    for channel in channels:
        clean_name = channel.username.strip().lstrip("@").lower()
        total_delta = channel_totals.get(clean_name, 0.0)
        p_count = post_counts_by_user.get(clean_name, 0)
        r_count = reels_counts_by_user.get(clean_name, 0)
        s_count = static_counts_by_user.get(clean_name, 0)
        views_per_post = total_delta / p_count if p_count > 0 else 0.0

        prev_metric_query = select(MonthlyChannelMetric.monthly_views).where(
            (MonthlyChannelMetric.instagram_id == channel.instagram_id)
            & (MonthlyChannelMetric.year_month == prev_year_month_str)
        )
        prev_metric_result = await db.execute(prev_metric_query)
        prev_views = prev_metric_result.scalar_one_or_none()

        growth_percent = None
        if prev_views and prev_views > 0:
            growth_percent = ((total_delta - prev_views) / prev_views) * 100

        stmt = insert(MonthlyChannelMetric).values(
            instagram_id=channel.instagram_id,
            username=channel.username,
            year_month=target_year_month,
            monthly_views=total_delta,
            previous_monthly_views=prev_views,
            growth_percent=growth_percent,
            post_count=p_count,
            reels_count=r_count,
            static_post_count=s_count,
            views_per_post=views_per_post,
            snapshot1_run_id=snapshot1_run_id,
            snapshot2_run_id=snapshot2_run_id,
        )

        do_update_stmt = stmt.on_conflict_do_update(
            constraint="uq_channel_month",
            set_={
                "username": stmt.excluded.username,
                "monthly_views": stmt.excluded.monthly_views,
                "previous_monthly_views": stmt.excluded.previous_monthly_views,
                "growth_percent": stmt.excluded.growth_percent,
                "post_count": stmt.excluded.post_count,
                "reels_count": stmt.excluded.reels_count,
                "static_post_count": stmt.excluded.static_post_count,
                "views_per_post": stmt.excluded.views_per_post,
                "snapshot1_run_id": stmt.excluded.snapshot1_run_id,
                "snapshot2_run_id": stmt.excluded.snapshot2_run_id,
                "calculated_at": func.now(),
            },
        )

        await db.execute(do_update_stmt)
        channels_processed += 1

    await db.commit()
    return {"channels_processed": channels_processed}

