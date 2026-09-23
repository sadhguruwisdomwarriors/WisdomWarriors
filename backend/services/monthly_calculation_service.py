import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from backend.models.micro_unit_channel import MicroUnitChannel
from backend.models.post_snapshot import PostSnapshot
from backend.models.monthly_channel_metric import MonthlyChannelMetric


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


def _extract_coauthors(raw_coauthors) -> list[str]:
    if not raw_coauthors:
        return []
    if isinstance(raw_coauthors, str):
        try:
            raw_coauthors = json.loads(raw_coauthors)
        except Exception:
            return []
    result = []
    if isinstance(raw_coauthors, list):
        for item in raw_coauthors:
            if isinstance(item, str):
                c = item.strip().lstrip("@").lower()
                if c and c not in result:
                    result.append(c)
            elif isinstance(item, dict):
                for k in ("username", "userName", "ownerUsername", "handle"):
                    val = item.get(k)
                    if isinstance(val, str) and val.strip():
                        c = val.strip().lstrip("@").lower()
                        if c and c not in result:
                            result.append(c)
                        break
    return result


async def _get_views_and_posts_for_snapshot_month(
    db: AsyncSession,
    run_id: int,
    month_str: str,
    target_usernames: set[str],
) -> tuple[dict[str, float], dict[str, int], dict[str, int], dict[str, int]]:
    stmt = (
        select(PostSnapshot)
        .where(
            (PostSnapshot.run_id == run_id)
            & (PostSnapshot.timestamp.is_not(None))
            & (func.to_char(PostSnapshot.timestamp, "YYYY-MM") == month_str)
        )
    )
    res = await db.execute(stmt)
    posts = res.scalars().all()

    views_by_user = {u: 0.0 for u in target_usernames}
    post_counts = {u: 0 for u in target_usernames}
    reels_counts = {u: 0 for u in target_usernames}
    static_counts = {u: 0 for u in target_usernames}

    for p in posts:
        owner = (p.owner_username or "").strip().lstrip("@").lower()
        coauthors = _extract_coauthors(p.coauthor_producers)
        participants = []
        for part in [owner, *coauthors]:
            if part and part not in participants:
                participants.append(part)

        if not participants:
            continue

        split_factor = max(1, len(participants))
        shared_views = float(p.video_play_count or 0) / split_factor

        is_reel = (
            (p.type in ("Video", "ReelVideo"))
            or (p.product_type == "clips")
            or bool(p.video_play_count and p.video_play_count > 0)
            or bool(p.video_view_count and p.video_view_count > 0)
        )

        for part in participants:
            if part in target_usernames:
                views_by_user[part] += shared_views
                post_counts[part] += 1
                if is_reel:
                    reels_counts[part] += 1
                else:
                    static_counts[part] += 1

    return views_by_user, post_counts, reels_counts, static_counts


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

    target_usernames = {
        c.username.strip().lstrip("@").lower()
        for c in channels
        if (getattr(c, "platform", "INSTAGRAM") or "INSTAGRAM").upper() == "INSTAGRAM"
    }

    channel_totals: dict[str, float] = {u: 0.0 for u in target_usernames}

    # 1. Calculate prior 6 months decay/growth delta (S2 - S1)
    for prior_m in prior_months:
        s1_views, _, _, _ = await _get_views_and_posts_for_snapshot_month(
            db=db,
            run_id=snapshot1_run_id,
            month_str=prior_m,
            target_usernames=target_usernames,
        )
        s2_views, _, _, _ = await _get_views_and_posts_for_snapshot_month(
            db=db,
            run_id=snapshot2_run_id,
            month_str=prior_m,
            target_usernames=target_usernames,
        )

        for uname in target_usernames:
            month_delta = max(0.0, s2_views[uname] - s1_views[uname])
            channel_totals[uname] += month_delta

    # 2. Add target month views and post counts directly from S2
    target_s2_views, post_counts_by_user, reels_counts_by_user, static_counts_by_user = (
        await _get_views_and_posts_for_snapshot_month(
            db=db,
            run_id=snapshot2_run_id,
            month_str=target_year_month,
            target_usernames=target_usernames,
        )
    )

    for uname in target_usernames:
        channel_totals[uname] += target_s2_views[uname]

    # 3. Upsert into monthly_channel_metrics
    prev_month_num = month - 1
    prev_year_num = year
    if prev_month_num <= 0:
        prev_month_num = 12
        prev_year_num -= 1
    prev_year_month_str = f"{prev_year_num}-{prev_month_num:02d}"

    channels_processed = 0

    for channel in channels:
        platform = (getattr(channel, "platform", "INSTAGRAM") or "INSTAGRAM").upper()
        if platform != "INSTAGRAM":
            continue

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

