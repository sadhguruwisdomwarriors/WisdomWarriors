import calendar
from datetime import datetime, timezone
import logging
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from backend.config import get_settings

logger = logging.getLogger(__name__)

_yt_engine = None

def get_youtube_engine():
    global _yt_engine
    settings = get_settings()
    yt_url = (settings.youtube_database_url or "").strip()
    if not yt_url:
        return None
    if _yt_engine is None:
        # Normalize connection string for asyncpg if needed
        if yt_url.startswith("postgresql://") and not yt_url.startswith("postgresql+asyncpg://"):
            yt_url = yt_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        try:
            _yt_engine = create_async_engine(
                yt_url,
                echo=False,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
        except Exception as e:
            logger.error(f"Error creating YouTube DB engine: {e}")
            return None
    return _yt_engine


async def fetch_available_youtube_channels() -> list[dict[str, Any]]:
    """
    Fetch all active YouTube channels from the YouTube database (read-only).
    """
    engine = get_youtube_engine()
    if not engine:
        return []

    try:
        async with engine.connect() as conn:
            query = text("""
                SELECT 
                    id, 
                    youtube_channel_id, 
                    title, 
                    custom_url, 
                    thumbnail_url, 
                    category,
                    current_subscribers,
                    current_views,
                    current_video_count
                FROM channels
                WHERE deleted_at IS NULL AND (status IS NULL OR status != 'archived')
                ORDER BY title ASC
            """)
            result = await conn.execute(query)
            rows = result.mappings().all()
            return [
                {
                    "id": str(r["id"]),
                    "youtube_channel_id": r["youtube_channel_id"] or "",
                    "title": r["title"] or r["custom_url"] or r["youtube_channel_id"] or "Untitled Channel",
                    "custom_url": r["custom_url"] or "",
                    "thumbnail_url": r["thumbnail_url"] or "",
                    "category": r["category"] or "",
                    "current_subscribers": int(r["current_subscribers"] or 0),
                    "current_views": int(r["current_views"] or 0),
                    "current_video_count": int(r["current_video_count"] or 0),
                }
                for r in rows
            ]
    except Exception as e:
        logger.error(f"Error fetching YouTube channels from DB: {e}")
        return []


async def calculate_youtube_monthly_metrics(
    channel_ids: list[str], 
    year: int, 
    month: int
) -> dict[str, dict[str, Any]]:
    """
    Computes period views growth and video upload count for the specified YouTube channels in a given month.
    channel_ids can contain youtube_channel_id or the internal channel UUID.
    Returns: { channel_identifier: { "views": float, "video_count": int, "title": str } }
    """
    if not channel_ids:
        return {}

    engine = get_youtube_engine()
    if not engine:
        # Fallback when YouTube database is not yet linked
        return {
            cid: {"views": 0.0, "video_count": 0, "title": ""}
            for cid in channel_ids
        }

    _, last_day = calendar.monthrange(year, month)
    start_dt = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    metrics_by_channel: dict[str, dict[str, Any]] = {
        cid: {"views": 0.0, "video_count": 0, "title": ""}
        for cid in channel_ids
    }

    try:
        async with engine.connect() as conn:
            # First, resolve internal channel IDs and titles
            res_channels = await conn.execute(
                text("""
                    SELECT id, youtube_channel_id, title, custom_url
                    FROM channels
                    WHERE id = ANY(:cids) OR youtube_channel_id = ANY(:cids) OR custom_url = ANY(:cids)
                """),
                {"cids": channel_ids}
            )
            ch_rows = res_channels.mappings().all()
            internal_ids = [r["id"] for r in ch_rows]
            id_to_ident = {}
            for r in ch_rows:
                title = r["title"] or r["custom_url"] or r["youtube_channel_id"]
                for cid in channel_ids:
                    if cid in (r["id"], r["youtube_channel_id"], r["custom_url"]):
                        id_to_ident[r["id"]] = cid
                        metrics_by_channel[cid]["title"] = title

            if not internal_ids:
                return metrics_by_channel

            # 1. Count uploaded videos published in target month
            upload_query = text("""
                SELECT channel_id, COUNT(id) AS video_count
                FROM videos
                WHERE channel_id = ANY(:int_ids)
                  AND deleted_at IS NULL
                  AND published_at >= :start_dt
                  AND published_at <= :end_dt
                GROUP BY channel_id
            """)
            upload_res = await conn.execute(
                upload_query,
                {"int_ids": internal_ids, "start_dt": start_dt, "end_dt": end_dt}
            )
            for r in upload_res.mappings().all():
                ident = id_to_ident.get(r["channel_id"])
                if ident and ident in metrics_by_channel:
                    metrics_by_channel[ident]["video_count"] = int(r["video_count"] or 0)

            # 2. Compute delta views from video_snapshots using opening/closing snapshot logic
            grace_ms = 2 * 24 * 60 * 60 * 1000 # 2 grace days
            period_views_query = text("""
                WITH target_videos AS (
                  SELECT v.id AS video_id, v.channel_id, v.published_at
                  FROM videos v
                  WHERE v.channel_id = ANY(:int_ids)
                    AND v.deleted_at IS NULL
                ),
                per_video AS (
                  SELECT
                    tv.video_id,
                    tv.channel_id,
                    tv.published_at,
                    (
                      SELECT MIN(s.date) FROM video_snapshots s
                      WHERE s.video_id = tv.video_id
                        AND s.deleted_at IS NULL
                    ) AS first_snap_date,
                    (
                      SELECT s.views FROM video_snapshots s
                      WHERE s.video_id = tv.video_id
                        AND s.deleted_at IS NULL
                        AND s.date < :start_dt
                      ORDER BY s.date DESC
                      LIMIT 1
                    ) AS opening_views,
                    (
                      SELECT s.views FROM video_snapshots s
                      WHERE s.video_id = tv.video_id
                        AND s.deleted_at IS NULL
                        AND s.date >= :start_dt
                        AND s.date <= :end_dt
                      ORDER BY s.date ASC
                      LIMIT 1
                    ) AS first_in_range_views,
                    (
                      SELECT s.views FROM video_snapshots s
                      WHERE s.video_id = tv.video_id
                        AND s.deleted_at IS NULL
                        AND s.date <= :end_dt
                      ORDER BY s.date DESC
                      LIMIT 1
                    ) AS closing_views
                  FROM target_videos tv
                ),
                per_video_delta AS (
                  SELECT
                    channel_id,
                    GREATEST(
                      0::bigint,
                      closing_views
                      - CASE
                          WHEN opening_views IS NOT NULL THEN opening_views
                          WHEN published_at IS NOT NULL
                               AND first_snap_date IS NOT NULL
                               AND (EXTRACT(EPOCH FROM (first_snap_date - published_at)) * 1000) <= :grace_ms
                            THEN 0::bigint
                          ELSE COALESCE(first_in_range_views, 0::bigint)
                        END
                    ) AS delta
                  FROM per_video
                  WHERE closing_views IS NOT NULL
                )
                SELECT channel_id, SUM(delta) AS total_views
                FROM per_video_delta
                GROUP BY channel_id
            """)
            views_res = await conn.execute(
                period_views_query,
                {"int_ids": internal_ids, "start_dt": start_dt, "end_dt": end_dt, "grace_ms": grace_ms}
            )
            for r in views_res.mappings().all():
                ident = id_to_ident.get(r["channel_id"])
                if ident and ident in metrics_by_channel:
                    metrics_by_channel[ident]["views"] = float(r["total_views"] or 0.0)

    except Exception as e:
        logger.error(f"Error calculating YouTube monthly metrics: {e}")

    return metrics_by_channel
