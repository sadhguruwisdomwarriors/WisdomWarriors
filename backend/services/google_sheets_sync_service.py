import asyncio
import csv
import io
import json
import logging
import re
import ssl
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from backend.models.scrape_profile import ScrapeProfile
from backend.models.profile import Profile
from backend.models.profile_handle_history import ProfileHandleHistory
from backend.repositories.scrape_profile_repo import add_scrape_profiles_bulk, update_scrape_profile_fields

logger = logging.getLogger(__name__)

SPREADSHEET_ID = "1rF7tGOjn5gdEWnn3DEwao51wPvDIf2xLgD_WJk47xA0"

GRADE_TABS = [
    {"name": "Grade A", "gid": "0", "grade": "A"},
    {"name": "Grade B", "gid": "1853726635", "grade": "B"},
    {"name": "Grade C", "gid": "690782911", "grade": "C"},
    {"name": "Grade D", "gid": "859249885", "grade": "D"},
    {"name": "Grade E", "gid": "200360753", "grade": "E"},
]

INVALID_TERMS = {
    "na", "n/a", "nil", "none", "not created", "not yet", "not yet made",
    "work in progress", "don't have any", "dont have any", "no", "-", "--",
    "not decided yet", "reels", "p", "explore", "stories", "share", "tags",
    "about", "help", "instagram", "https", "http", "www", "null", "undefined",
    "reel", "tv", "profile", "user", "post", "posts"
}

SKIP_PHRASES = {
    "na", "n/a", "nil", "none", "no", "no account", "dont have", "don't have",
    "does not have", "does not have (yet)", "not created", "not yet", "not yet made",
    "work in progress", "will share", "will share once ready", "not decided",
    "not decided yet", "no channel", "no link", "not sure", "not applicable",
    "-", "--", ".", "...", "", "no insta", "no instagram", "no insta account", "nil."
}

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


def is_empty_or_placeholder(text_content: str) -> bool:
    """
    Checks if a cell is empty or contains placeholder / skip phrases.
    """
    if not text_content:
        return True
    cleaned = text_content.strip().lower()
    if not cleaned or cleaned in SKIP_PHRASES:
        return True
    return any(cleaned == phrase or cleaned.startswith(phrase + " ") or cleaned.startswith(phrase + "(") for phrase in SKIP_PHRASES)


def has_attempted_instagram_link(ig_link_cell: str, ig_name_cell: str) -> bool:
    """
    Determines if the creator provided an actual Instagram link/handle in the sheet,
    as opposed to leaving it empty, putting placeholders (NA, nil), or writing plain non-handle text.
    """
    link_clean = ig_link_cell.strip()
    name_clean = ig_name_cell.strip()

    # If both are empty or placeholders, no IG link was provided
    if (not link_clean or is_empty_or_placeholder(link_clean)) and (not name_clean or is_empty_or_placeholder(name_clean)):
        return False

    # Check if there is an attempted URL or @handle
    if "instagram.com" in link_clean.lower() or "instagram.com" in name_clean.lower():
        return True
    if link_clean.startswith("@") or name_clean.startswith("@"):
        return True
    if link_clean.startswith("http://") or link_clean.startswith("https://") or link_clean.startswith("www."):
        return True

    # If link_clean is a single alphanumeric username (no spaces, len >= 3)
    if link_clean and not is_empty_or_placeholder(link_clean) and " " not in link_clean and len(link_clean) >= 3:
        return True

    # If name_clean is a single alphanumeric username (no spaces, len >= 3) and link_cell is empty/placeholder
    if name_clean and not is_empty_or_placeholder(name_clean) and " " not in name_clean and len(name_clean) >= 3:
        return True

    return False


def extract_instagram_handles(text_content: str) -> List[str]:
    """
    Extracts all valid Instagram handles from a string that may contain multiple links,
    handles, or freeform text across multiple lines or comma-separated values.
    """
    if not text_content or is_empty_or_placeholder(text_content):
        return []

    text_content = text_content.replace("\\n", "\n").replace("\\r", "")
    handles = []

    # 1. Direct Regex for all Instagram URLs anywhere in the string
    for m in re.finditer(r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9._]+)', text_content, re.IGNORECASE):
        h = m.group(1).strip().rstrip('/')
        if h.lower() not in INVALID_TERMS and not h.lower().startswith("share") and not is_empty_or_placeholder(h):
            handles.append(h.lstrip('@').lower())

    # 2. Extract @handles
    for m in re.finditer(r'@([a-zA-Z0-9._]+)', text_content):
        h = m.group(1).strip()
        if h.lower() not in INVALID_TERMS and not is_empty_or_placeholder(h):
            handles.append(h.lstrip('@').lower())

    # 3. If no URLs or @handles were found, check if lines or comma-separated tokens are valid usernames
    if not handles:
        tokens = re.split(r'[\r\n,;|]+', text_content)
        for token in tokens:
            raw = token.strip().lstrip('@')
            if not raw or " " in raw or raw.startswith("http") or is_empty_or_placeholder(raw):
                continue
            if re.match(r'^[a-zA-Z0-9._]{3,30}$', raw):
                if raw.lower() not in INVALID_TERMS:
                    handles.append(raw.lower())

    # Deduplicate preserving order
    seen = set()
    result = []
    for h in handles:
        if h not in seen:
            seen.add(h)
            result.append(h)
    return result


def fetch_tab_csv_sync(gid: str) -> str:
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read().decode("utf-8", errors="replace")


def check_instagram_handle_live_sync(handle: str) -> str:
    """
    Synchronously verifies whether an Instagram account is accessible, deleted/404, or invalid.
    Returns: "VALID" | "DELETED" | "INVALID"
    """
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={handle}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "x-ig-app-id": "936619743392459",
        "Accept": "*/*",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=ssl_context, timeout=6) as response:
            data = json.loads(response.read().decode("utf-8"))
            user = data.get("data", {}).get("user")
            if user:
                return "VALID"
            else:
                return "DELETED"
    except urllib.error.HTTPError as e:
        if e.code == 404 or e.code == 410:
            return "DELETED"
        # 429 rate limit or 302 redirect means endpoint/account exists
        return "VALID"
    except urllib.error.URLError:
        return "INVALID"
    except Exception:
        return "VALID"


async def check_handles_live_concurrent(handles: List[str]) -> Dict[str, str]:
    """
    Checks multiple handles concurrently using run_in_executor.
    """
    loop = asyncio.get_running_loop()
    semaphore = asyncio.Semaphore(15)

    async def check_one(h: str):
        async with semaphore:
            return h, await loop.run_in_executor(None, check_instagram_handle_live_sync, h)

    tasks = [check_one(h) for h in handles]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    status_map = {}
    for res in results:
        if isinstance(res, tuple):
            h, st = res
            status_map[h] = st
        elif isinstance(res, Exception):
            pass
    return status_map


async def analyze_google_sheets(db: AsyncSession) -> Dict[str, Any]:
    """
    Fetches Grade A-E tabs:
    1. Skips rows where no Instagram link is present in the sheet (never shows in Link Invalid).
    2. Step 1: Checks Database first (Profile ID / Username) -> Already Tracked / Handle Changed.
    3. Step 2: Checks live reachability -> Link Invalid (broken link) vs Channel Deleted (404/deleted) vs New Channel.
    """
    import asyncio
    
    scrape_profiles_res = await db.execute(select(ScrapeProfile))
    all_scrape_profiles = scrape_profiles_res.scalars().all()
    
    existing_handles_map: Dict[str, ScrapeProfile] = {
        p.username.lower(): p for p in all_scrape_profiles if p.username
    }

    raw_items: List[Dict[str, Any]] = []
    summary = {
        "total_rows_scanned": 0,
        "new_channels": 0,
        "handle_changed": 0,
        "link_invalid": 0,
        "channel_deleted": 0,
        "already_tracked": 0,
    }

    seen_channel_keys = set()
    candidate_handles_to_check = set()
    loop = asyncio.get_running_loop()

    for tab in GRADE_TABS:
        try:
            csv_text = await loop.run_in_executor(None, fetch_tab_csv_sync, tab["gid"])
        except Exception as e:
            logger.error(f"Error fetching tab {tab['name']} ({tab['gid']}): {e}")
            continue

        reader = csv.reader(io.StringIO(csv_text))
        header_row = None
        col_id = 0
        col_name = 1
        col_ig_name = 17
        col_ig_link = 18
        col_yt_link = 14

        for row_idx, row in enumerate(reader):
            if not row:
                continue

            if "ID" in row and ("Instagram" in "".join(row) or "Channel" in "".join(row) or "Full Name" in row):
                header_row = row
                for idx, cell in enumerate(row):
                    cell_clean = cell.strip().lower()
                    if cell_clean == "id":
                        col_id = idx
                    elif "full name" in cell_clean:
                        col_name = idx
                    elif "instagram channel name" in cell_clean:
                        col_ig_name = idx
                    elif "instagram channel link" in cell_clean:
                        col_ig_link = idx
                    elif "channel link" in cell_clean and "instagram" not in cell_clean:
                        col_yt_link = idx
                continue

            if not header_row:
                continue

            member_id = row[col_id].strip() if len(row) > col_id else ""
            if not member_id or not member_id.upper().startswith("SWW"):
                continue

            summary["total_rows_scanned"] += 1
            creator_name = row[col_name].strip() if len(row) > col_name else ""
            
            ig_link_cell = row[col_ig_link].strip() if len(row) > col_ig_link else ""
            ig_name_cell = row[col_ig_name].strip() if len(row) > col_ig_name else ""
            yt_link_cell = row[col_yt_link].strip() if len(row) > col_yt_link else ""

            # Check if an Instagram link was actually provided
            if not has_attempted_instagram_link(ig_link_cell, ig_name_cell):
                # Also check if YouTube column was accidentally used for an Instagram URL
                if "instagram.com" not in yt_link_cell.lower():
                    # NO Instagram link provided in sheet -> Completely omit from Google Sync!
                    continue

            # Gather raw inputs for handle extraction
            raw_channel_inputs = [c for c in [ig_link_cell, ig_name_cell] if c.strip() and not is_empty_or_placeholder(c)]
            if "instagram.com" in yt_link_cell.lower():
                raw_channel_inputs.append(yt_link_cell.strip())

            combined_ig_text = "\n".join(raw_channel_inputs)
            extracted_handles = extract_instagram_handles(combined_ig_text)

            # If an Instagram link was provided, but the URL is broken / malformed -> Link Invalid
            if not extracted_handles:
                raw_display = ig_link_cell or ig_name_cell or "Malformed link"
                raw_items.append({
                    "channel_id": member_id,
                    "creator_name": creator_name,
                    "username": "",
                    "instagram_url": "",
                    "raw_input": raw_display,
                    "grade": tab["grade"],
                    "category": "Dedicated",
                    "tab_name": tab["name"],
                    "case_type": "LINK_INVALID",
                    "status_label": "Link Invalid",
                    "status_color": "red",
                    "can_add": False,
                })
                summary["link_invalid"] += 1
                continue

            # Process each valid handle
            for handle in extracted_handles:
                unique_key = f"{member_id}_{handle}"
                if unique_key in seen_channel_keys:
                    continue
                seen_channel_keys.add(unique_key)

                instagram_url = f"https://www.instagram.com/{handle}/"

                # STEP 1: Database Check
                if handle in existing_handles_map:
                    raw_items.append({
                        "channel_id": member_id,
                        "creator_name": creator_name,
                        "username": handle,
                        "instagram_url": instagram_url,
                        "raw_input": ig_link_cell or handle,
                        "grade": tab["grade"],
                        "category": "Dedicated",
                        "tab_name": tab["name"],
                        "case_type": "ALREADY_TRACKED",
                        "status_label": "Already Tracked",
                        "status_color": "gray",
                        "can_add": False,
                    })
                    summary["already_tracked"] += 1
                else:
                    # Candidate new channel -> queue for live reachability check
                    candidate_handles_to_check.add(handle)
                    raw_items.append({
                        "channel_id": member_id,
                        "creator_name": creator_name,
                        "username": handle,
                        "instagram_url": instagram_url,
                        "raw_input": ig_link_cell or handle,
                        "grade": tab["grade"],
                        "category": "Dedicated",
                        "tab_name": tab["name"],
                        "case_type": "PENDING_CHECK",
                        "status_label": "Checking...",
                        "status_color": "green",
                        "can_add": True,
                    })

    # STEP 2: Verify candidate new channels live for deleted / invalid / valid
    if candidate_handles_to_check:
        live_status_map = await check_handles_live_concurrent(list(candidate_handles_to_check))
    else:
        live_status_map = {}

    final_items: List[Dict[str, Any]] = []
    for item in raw_items:
        if item["case_type"] == "PENDING_CHECK":
            h = item["username"]
            st = live_status_map.get(h, "VALID")
            if st == "DELETED":
                item["case_type"] = "CHANNEL_DELETED"
                item["status_label"] = "Channel Deleted / Not Found"
                item["status_color"] = "red"
                item["can_add"] = False
                summary["channel_deleted"] += 1
            elif st == "INVALID":
                item["case_type"] = "LINK_INVALID"
                item["status_label"] = "Link Invalid"
                item["status_color"] = "red"
                item["can_add"] = False
                summary["link_invalid"] += 1
            else:
                item["case_type"] = "NEW_CHANNEL"
                item["status_label"] = "New Channel"
                item["status_color"] = "green"
                item["can_add"] = True
                summary["new_channels"] += 1
        final_items.append(item)

    return {
        "summary": summary,
        "items": final_items,
    }


async def apply_google_sheets_sync(
    db: AsyncSession,
    channels_to_add: List[Dict[str, Any]],
    handles_to_update: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Applies the selected new channels to scrape_profiles and updates changed handles.
    """
    added_count = 0
    updated_count = 0

    if channels_to_add:
        payload = [
            {
                "username": item["username"],
                "category": item.get("category", "Dedicated"),
                "grade": item.get("grade", "E"),
            }
            for item in channels_to_add
            if item.get("username")
        ]
        created, _ = await add_scrape_profiles_bulk(db, payload)
        added_count = len(created)

    if handles_to_update:
        for update_item in handles_to_update:
            profile_id = update_item.get("profile_id")
            new_username = update_item.get("new_username")
            if profile_id and new_username:
                await update_scrape_profile_fields(
                    db,
                    profile_id,
                    username=new_username,
                    set_fields={"username"}
                )
                updated_count += 1

    await db.commit()

    return {
        "status": "success",
        "added_count": added_count,
        "updated_count": updated_count,
    }
