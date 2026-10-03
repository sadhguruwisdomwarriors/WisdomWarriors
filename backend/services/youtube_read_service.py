import calendar
import json
import logging
import urllib.request
import urllib.parse
import ssl
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy import text
from backend.config import get_settings

logger = logging.getLogger(__name__)

# SSL context for HTTPS REST requests fallback
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

GRACE_MS = 2 * 24 * 3600 * 1000  # 2 days fresh tracking grace period

_yt_engine: AsyncEngine | None = None

def get_youtube_engine() -> AsyncEngine | None:
    global _yt_engine
    if _yt_engine is not None:
        return _yt_engine
    settings = get_settings()
    db_url = settings.youtube_database_url or "postgresql+asyncpg://postgres.vsxgzvduphqqcpwwrhzt:%26g%40weY_G6E2%237Kn@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"
    if not db_url:
        return None
    try:
        _yt_engine = create_async_engine(
            db_url,
            connect_args={"statement_cache_size": 0},
            pool_size=5,
            max_overflow=2,
            pool_pre_ping=True
        )
        return _yt_engine
    except Exception as e:
        logger.error(f"Error creating YouTube DB engine: {e}")
        return None

def _get_rest_headers():
    settings = get_settings()
    key = settings.youtube_supabase_key or ""
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }

async def fetch_available_youtube_channels() -> list[dict[str, Any]]:
    """
    Fetch all active YouTube channels from the YouTube Supabase database (read-only).
    Uses direct database query if possible, with REST API fallback.
    """
    engine = get_youtube_engine()
    if engine:
        try:
            async with engine.connect() as conn:
                res = await conn.execute(text("""
                    SELECT id, youtube_channel_id, title, custom_url, thumbnail_url, category,
                           current_subscribers, current_views, current_video_count
                    FROM channels
                    WHERE deleted_at IS NULL AND (status IS NULL OR status != 'archived')
                    ORDER BY title ASC
                """))
                rows = res.mappings().all()
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
            logger.warning(f"Direct DB query failed in fetch_available_youtube_channels, falling back to REST: {e}")

    # Fallback to REST API
    settings = get_settings()
    base_url = (settings.youtube_supabase_url or "").rstrip("/")
    key = settings.youtube_supabase_key

    if not base_url or not key:
        return []

    try:
        url = f"{base_url}/rest/v1/channels?deleted_at=is.null&select=id,youtube_channel_id,title,custom_url,thumbnail_url,category,current_subscribers,current_views,current_video_count&order=title.asc"
        req = urllib.request.Request(url, headers=_get_rest_headers())
        with urllib.request.urlopen(req, context=_ssl_ctx, timeout=10) as r:
            rows = json.loads(r.read().decode("utf-8"))
            return [
                {
                    "id": str(r.get("id")),
                    "youtube_channel_id": r.get("youtube_channel_id") or "",
                    "title": r.get("title") or r.get("custom_url") or r.get("youtube_channel_id") or "Untitled Channel",
                    "custom_url": r.get("custom_url") or "",
                    "thumbnail_url": r.get("thumbnail_url") or "",
                    "category": r.get("category") or "",
                    "current_subscribers": int(r.get("current_subscribers") or 0),
                    "current_views": int(r.get("current_views") or 0),
                    "current_video_count": int(r.get("current_video_count") or 0),
                }
                for r in rows
            ]
    except Exception as e:
        logger.error(f"Error fetching YouTube channels via REST: {e}")
        return []


async def calculate_youtube_monthly_metrics(
    channel_ids: list[str], 
    year: int, 
    month: int
) -> dict[str, dict[str, Any]]:
    """
    Computes period views growth and video upload count for the specified YouTube channels in a given month,
    faithfully matching the exact Channel Report logic from the YouTube web app (videoSnapshotPeriodViews.js).
    channel_ids can contain internal ID, youtube_channel_id, custom_url, or channel title.
    Returns: { channel_identifier: { "views": float, "video_count": int, "title": str } }
    """
    if not channel_ids:
        return {}

    metrics_by_channel: dict[str, dict[str, Any]] = {
        cid: {"views": 0.0, "video_count": 0, "title": ""}
        for cid in channel_ids
    }

    _, last_day = calendar.monthrange(year, month)
    start_dt = datetime(year, month, 1, 0, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(year, month, last_day, 23, 59, 59, 999000, tzinfo=timezone.utc)

    engine = get_youtube_engine()
    if engine:
        try:
            async with engine.connect() as conn:
                # 1. Resolve channel IDs against the channels table
                res_channels = await conn.execute(
                    text("""
                        SELECT id, youtube_channel_id, title, custom_url
                        FROM channels
                        WHERE deleted_at IS NULL
                          AND (
                            id = ANY(:cids) 
                            OR youtube_channel_id = ANY(:cids) 
                            OR custom_url = ANY(:cids) 
                            OR title = ANY(:cids)
                          )
                    """),
                    {"cids": channel_ids}
                )
                ch_rows = res_channels.mappings().all()

                # If some channels weren't matched due to case differences, query case-insensitively
                matched_cids = set()
                for r in ch_rows:
                    for cid in channel_ids:
                        if cid in (r["id"], r["youtube_channel_id"], r["custom_url"], r["title"]):
                            matched_cids.add(cid)

                missing_cids = [cid for cid in channel_ids if cid not in matched_cids]
                if missing_cids:
                    res_extra = await conn.execute(
                        text("""
                            SELECT id, youtube_channel_id, title, custom_url
                            FROM channels
                            WHERE deleted_at IS NULL
                        """)
                    )
                    all_rows = res_extra.mappings().all()
                    for r in all_rows:
                        t_lower = (r["title"] or "").strip().lower()
                        u_lower = (r["custom_url"] or "").strip().lower()
                        y_id = (r["youtube_channel_id"] or "").strip()
                        c_id = str(r["id"]).strip()
                        for m_cid in missing_cids:
                            mc_clean = m_cid.strip().lower()
                            if mc_clean in (t_lower, u_lower, y_id.lower(), c_id.lower()):
                                ch_rows.append(r)
                                matched_cids.add(m_cid)

                # Map channel identifiers to internal IDs and titles
                ident_to_internal: dict[str, str] = {}
                for cid in channel_ids:
                    cid_clean = cid.strip().lower()
                    for r in ch_rows:
                        if cid in (r["id"], r["youtube_channel_id"], r["custom_url"], r["title"]) or \
                           cid_clean in ((r["title"] or "").strip().lower(), (r["custom_url"] or "").strip().lower()):
                            ident_to_internal[cid] = r["id"]
                            metrics_by_channel[cid]["title"] = r["title"] or r["custom_url"] or r["youtube_channel_id"] or cid
                            break

                internal_ids = list(set(ident_to_internal.values()))
                if not internal_ids:
                    return metrics_by_channel

                # 2. Uploaded video count in period (videos published in target month)
                upload_res = await conn.execute(
                    text("""
                        SELECT channel_id, COUNT(id) AS video_count
                        FROM videos
                        WHERE channel_id = ANY(:int_ids)
                          AND published_at >= :start_dt
                          AND published_at <= :end_dt
                          AND deleted_at IS NULL
                        GROUP BY channel_id
                    """),
                    {"int_ids": internal_ids, "start_dt": start_dt, "end_dt": end_dt}
                )
                vcount_by_internal = {r["channel_id"]: int(r["video_count"] or 0) for r in upload_res.mappings().all()}

                # 3. Exact period views delta (identical to videoSnapshotPeriodViews.js in the YouTube app)
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
                              -- preStart wins outright.
                              WHEN opening_views IS NOT NULL THEN opening_views
                              -- Freshly tracked: first snapshot within grace of publishedAt -> opening 0.
                              WHEN published_at IS NOT NULL
                                   AND first_snap_date IS NOT NULL
                                   AND (EXTRACT(EPOCH FROM (first_snap_date - published_at)) * 1000) <= :grace_ms
                                THEN 0::bigint
                              -- Else: first in-range snapshot as opaque baseline.
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
                    {"int_ids": internal_ids, "start_dt": start_dt, "end_dt": end_dt, "grace_ms": GRACE_MS}
                )
                views_by_internal = {r["channel_id"]: float(r["total_views"] or 0.0) for r in views_res.mappings().all()}

                # Populate metrics for each requested channel identifier
                for cid in channel_ids:
                    internal_id = ident_to_internal.get(cid)
                    if internal_id:
                        metrics_by_channel[cid]["views"] = views_by_internal.get(internal_id, 0.0)
                        metrics_by_channel[cid]["video_count"] = vcount_by_internal.get(internal_id, 0)

                return metrics_by_channel

        except Exception as e:
            logger.error(f"Direct DB query failed in calculate_youtube_monthly_metrics: {e}")

    return metrics_by_channel
