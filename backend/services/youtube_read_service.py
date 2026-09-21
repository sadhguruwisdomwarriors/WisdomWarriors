import calendar
import json
import logging
import urllib.request
import urllib.parse
import ssl
from datetime import datetime
from typing import Any
from backend.config import get_settings

logger = logging.getLogger(__name__)

# SSL context for HTTPS requests
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

GRACE_MS = 2 * 24 * 3600 * 1000  # 2 days fresh tracking grace period

def _get_rest_headers():
    settings = get_settings()
    key = settings.youtube_supabase_key or ""
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }

def _parse_iso(dt_str: str | None) -> float | None:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.timestamp() * 1000
    except Exception:
        return None

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
    Computes period views growth and video upload count for the specified YouTube channels in a given month,
    faithfully matching the exact Channel Report logic from the YouTube web app.
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
    start_str = f"{year}-{month:02d}-01T00:00:00.000Z"
    end_str = f"{year}-{month:02d}-{last_day:02d}T23:59:59.999Z"

    headers = _get_rest_headers()

    for cid in channel_ids:
        try:
            # 1. Query channel metadata
            or_filter = urllib.parse.quote(f"(id.eq.{cid},youtube_channel_id.eq.{cid},custom_url.eq.{cid},title.eq.{cid})")
            c_url = f"{base_url}/rest/v1/channels?or={or_filter}&deleted_at=is.null&select=id,youtube_channel_id,title,custom_url,current_views"
            req = urllib.request.Request(c_url, headers=headers)
            with urllib.request.urlopen(req, context=_ssl_ctx, timeout=10) as r:
                ch_data = json.loads(r.read().decode("utf-8"))
            
            if not ch_data:
                continue

            ch = ch_data[0]
            internal_id = ch.get("id")
            title = ch.get("title") or ch.get("custom_url") or ch.get("youtube_channel_id") or cid
            metrics_by_channel[cid]["title"] = title

            # 2. Count videos published in the target month (videosInPeriod)
            v_url = f"{base_url}/rest/v1/videos?channel_id=eq.{internal_id}&published_at=gte.{start_str}&published_at=lte.{end_str}&deleted_at=is.null&select=id"
            v_req = urllib.request.Request(v_url, headers=headers)
            with urllib.request.urlopen(v_req, context=_ssl_ctx, timeout=10) as r:
                vids_in_period = json.loads(r.read().decode("utf-8"))
            metrics_by_channel[cid]["video_count"] = len(vids_in_period) if isinstance(vids_in_period, list) else 0

            # 3. Check channel_snapshots first (Channel-level delta matching YouTube app Dashboard)
            cs_url = f"{base_url}/rest/v1/channel_snapshots?channel_id=eq.{internal_id}&deleted_at=is.null&order=date.asc&select=date,views"
            req = urllib.request.Request(cs_url, headers=headers)
            with urllib.request.urlopen(req, context=_ssl_ctx, timeout=8) as r:
                cs_snaps = json.loads(r.read().decode("utf-8"))

            if cs_snaps and len(cs_snaps) > 0:
                pre_cs = [s for s in cs_snaps if s.get("date") < start_str]
                post_cs = [s for s in cs_snaps if s.get("date") <= end_str]
                in_cs = [s for s in cs_snaps if start_str <= s.get("date") <= end_str]
                if post_cs and (pre_cs or in_cs):
                    cs_open = float(pre_cs[-1].get("views", 0) if pre_cs else in_cs[0].get("views", 0))
                    cs_close = float(post_cs[-1].get("views", 0))
                    metrics_by_channel[cid]["views"] = max(0.0, cs_close - cs_open)
                    continue

            # 4. Fallback to video_snapshots if channel_snapshots are not available
            all_videos = []
            offset = 0
            while True:
                v_all_url = f"{base_url}/rest/v1/videos?channel_id=eq.{internal_id}&deleted_at=is.null&select=id,published_at&limit=1000&offset={offset}"
                req = urllib.request.Request(v_all_url, headers=headers)
                with urllib.request.urlopen(req, context=_ssl_ctx, timeout=10) as r:
                    batch = json.loads(r.read().decode("utf-8"))
                if not batch or not isinstance(batch, list):
                    break
                all_videos.extend(batch)
                if len(batch) < 1000:
                    break
                offset += 1000

            if not all_videos:
                metrics_by_channel[cid]["views"] = 0.0
                continue

            video_ids = [v["id"] for v in all_videos]
            video_map = {v["id"]: v for v in all_videos}

            # Batch query video_snapshots for these videos (chunks of 100)
            snaps_by_video: dict[str, list[dict]] = {}
            chunk_size = 100
            for i in range(0, len(video_ids), chunk_size):
                chunk = video_ids[i:i + chunk_size]
                in_str = urllib.parse.quote(f"({','.join(chunk)})")
                s_offset = 0
                while True:
                    s_url = f"{base_url}/rest/v1/video_snapshots?video_id=in.{in_str}&deleted_at=is.null&order=date.asc&select=video_id,date,views&limit=1000&offset={s_offset}"
                    req = urllib.request.Request(s_url, headers=headers)
                    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=10) as r:
                        s_batch = json.loads(r.read().decode("utf-8"))
                    if not s_batch or not isinstance(s_batch, list):
                        break
                    for s in s_batch:
                        vid = s.get("video_id")
                        if vid not in snaps_by_video:
                            snaps_by_video[vid] = []
                        snaps_by_video[vid].append(s)
                    if len(s_batch) < 1000:
                        break
                    s_offset += 1000

            # Compute period views delta per video
            total_views = 0.0
            for vid, snaps in snaps_by_video.items():
                if not snaps:
                    continue

                closing_snaps = [s for s in snaps if s.get("date") <= end_str]
                if not closing_snaps:
                    continue
                closing_views = float(closing_snaps[-1].get("views") or 0)

                pre_start_snaps = [s for s in snaps if s.get("date") < start_str]
                in_range_snaps = [s for s in snaps if start_str <= s.get("date") <= end_str]

                v_info = video_map.get(vid, {})
                pub_str = v_info.get("published_at")
                first_snap_str = snaps[0].get("date")

                if pre_start_snaps:
                    opening_views = float(pre_start_snaps[-1].get("views") or 0)
                else:
                    pub_ms = _parse_iso(pub_str)
                    first_snap_ms = _parse_iso(first_snap_str)
                    if pub_ms is not None and first_snap_ms is not None and (first_snap_ms - pub_ms) <= GRACE_MS:
                        opening_views = 0.0
                    elif in_range_snaps:
                        opening_views = float(in_range_snaps[0].get("views") or 0)
                    else:
                        opening_views = 0.0

                delta = max(0.0, closing_views - opening_views)
                total_views += delta

            metrics_by_channel[cid]["views"] = total_views

        except Exception as ch_err:
            logger.error(f"Error calculating metrics for YouTube channel {cid}: {ch_err}")

    return metrics_by_channel
