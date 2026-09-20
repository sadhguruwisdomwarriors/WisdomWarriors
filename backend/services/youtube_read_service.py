import calendar
import json
import logging
import urllib.request
import urllib.parse
import ssl
from typing import Any
from backend.config import get_settings

logger = logging.getLogger(__name__)

# SSL context for HTTPS requests
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

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
    """
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
    Computes period views growth and video upload count for the specified YouTube channels in a given month.
    channel_ids can contain internal ID, youtube_channel_id, or custom_url.
    Returns: { channel_identifier: { "views": float, "video_count": int, "title": str } }
    """
    if not channel_ids:
        return {}

    settings = get_settings()
    base_url = (settings.youtube_supabase_url or "").rstrip("/")
    key = settings.youtube_supabase_key

    metrics_by_channel: dict[str, dict[str, Any]] = {
        cid: {"views": 0.0, "video_count": 0, "title": ""}
        for cid in channel_ids
    }

    if not base_url or not key:
        return metrics_by_channel

    _, last_day = calendar.monthrange(year, month)
    start_str = f"{year}-{month:02d}-01T00:00:00Z"
    end_str = f"{year}-{month:02d}-{last_day:02d}T23:59:59Z"

    headers = _get_rest_headers()

    for cid in channel_ids:
        try:
            # 1. Query channel metadata
            or_filter = urllib.parse.quote(f"(id.eq.{cid},youtube_channel_id.eq.{cid},custom_url.eq.{cid})")
            c_url = f"{base_url}/rest/v1/channels?or={or_filter}&select=id,youtube_channel_id,title,custom_url,current_views"
            req = urllib.request.Request(c_url, headers=headers)
            with urllib.request.urlopen(req, context=_ssl_ctx, timeout=8) as r:
                ch_data = json.loads(r.read().decode("utf-8"))
            
            if not ch_data:
                continue

            ch = ch_data[0]
            internal_id = ch.get("id")
            title = ch.get("title") or ch.get("custom_url") or ch.get("youtube_channel_id") or cid
            metrics_by_channel[cid]["title"] = title

            # 2. Count videos published in the target month
            v_url = f"{base_url}/rest/v1/videos?channel_id=eq.{internal_id}&published_at=gte.{start_str}&published_at=lte.{end_str}&select=id"
            v_req = urllib.request.Request(v_url, headers=headers)
            with urllib.request.urlopen(v_req, context=_ssl_ctx, timeout=8) as r:
                vids = json.loads(r.read().decode("utf-8"))
                metrics_by_channel[cid]["video_count"] = len(vids)

            # 3. Calculate period views growth using channel_snapshots
            s_url = f"{base_url}/rest/v1/channel_snapshots?channel_id=eq.{internal_id}&order=date.asc&select=date,views"
            s_req = urllib.request.Request(s_url, headers=headers)
            with urllib.request.urlopen(s_req, context=_ssl_ctx, timeout=8) as r:
                snapshots = json.loads(r.read().decode("utf-8"))

            if snapshots:
                pre_start_snaps = [s for s in snapshots if s.get("date") < start_str]
                in_range_snaps = [s for s in snapshots if s.get("date") >= start_str and s.get("date") <= end_str]
                post_end_snaps = [s for s in snapshots if s.get("date") <= end_str]

                opening_views = pre_start_snaps[-1].get("views", 0) if pre_start_snaps else (in_range_snaps[0].get("views", 0) if in_range_snaps else 0)
                closing_views = post_end_snaps[-1].get("views", 0) if post_end_snaps else (snapshots[-1].get("views", 0) if snapshots else opening_views)

                delta = max(0.0, float(closing_views) - float(opening_views))
                metrics_by_channel[cid]["views"] = delta
            else:
                metrics_by_channel[cid]["views"] = 0.0

        except Exception as ch_err:
            logger.error(f"Error calculating metrics for YouTube channel {cid}: {ch_err}")

    return metrics_by_channel
