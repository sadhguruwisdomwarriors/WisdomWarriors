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
    {"name": "Inactive", "gid": "157504391", "grade": "Inactive"},
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
        if not is_empty_or_placeholder(h) and not h.lower().startswith("share") and h.lower() not in INVALID_TERMS:
            handles.append(h.lstrip('@').lower())

    # 2. Extract @handles
    for m in re.finditer(r'@([a-zA-Z0-9._]+)', text_content):
        h = m.group(1).strip()
        if not is_empty_or_placeholder(h) and h.lower() not in INVALID_TERMS:
            handles.append(h.lstrip('@').lower())

    # 3. If no URLs or @handles were found, check if lines or comma-separated tokens are valid usernames
    if not handles:
        tokens = re.split(r'[\r\n,;|]+', text_content)
        for token in tokens:
            raw = token.strip().lstrip('@')
            if not raw or " " in raw or raw.startswith("http") or is_empty_or_placeholder(raw):
                continue
            if re.match(r'^[a-zA-Z0-9._]{3,30}$', raw) and raw.lower() not in INVALID_TERMS:
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


def check_instagram_handle_live_sync(handle: str) -> Dict[str, Any]:
    """
    Synchronously verifies whether an Instagram account is accessible, deleted/404, or invalid.
    Returns: {"status": "VALID" | "DELETED" | "INVALID", "user_id": Optional[str], "username": Optional[str]}
    """
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={handle}"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
        "x-ig-app-id": "936619743392459",
        "Accept": "*/*",
        "Sec-Fetch-Site": "same-origin",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=ssl_context, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
            user = data.get("data", {}).get("user")
            if user and user.get("id"):
                return {"status": "VALID", "user_id": str(user.get("id")), "username": user.get("username")}
            else:
                return {"status": "DELETED", "user_id": None, "username": None}
    except urllib.error.HTTPError as e:
        if e.code in [404, 410, 400]:
            return {"status": "DELETED", "user_id": None, "username": None}
        return {"status": "DELETED", "user_id": None, "username": None}
    except urllib.error.URLError:
        return {"status": "INVALID", "user_id": None, "username": None}
    except Exception:
        return {"status": "DELETED", "user_id": None, "username": None}


async def check_handles_live_concurrent(handles: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Checks multiple handles concurrently with controlled concurrency.
    """
    loop = asyncio.get_running_loop()
    semaphore = asyncio.Semaphore(10)

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
    Fetches Grade A-E + Inactive tabs:
    1. Skips rows where no Instagram link is present in the sheet.
    2. Step 1: Checks Database first (Channel ID / Profile Handle History) -> Already Tracked vs Handle Changed.
    3. Step 2: Checks live reachability -> Link Invalid (broken link) vs Channel Deleted (404/deleted) vs New Channel.
    """
    import asyncio
    
    # 1. Load scrape_profiles
    scrape_profiles_res = await db.execute(select(ScrapeProfile))
    all_scrape_profiles = scrape_profiles_res.scalars().all()
    
    sp_by_username: Dict[str, ScrapeProfile] = {
        p.username.lower(): p for p in all_scrape_profiles if p.username
    }
    sp_by_ig_id: Dict[str, ScrapeProfile] = {
        str(p.instagram_id): p for p in all_scrape_profiles if p.instagram_id
    }

    # 2. Load profiles
    profiles_res = await db.execute(select(Profile))
    all_profiles = profiles_res.scalars().all()
    profile_by_id: Dict[str, Profile] = {
        str(p.id): p for p in all_profiles if p.id
    }
    profile_by_username: Dict[str, Profile] = {
        p.username.lower(): p for p in all_profiles if p.username
    }

    # 3. Load profile_handle_history
    history_res = await db.execute(select(ProfileHandleHistory))
    all_history = history_res.scalars().all()
    history_to_pid: Dict[str, str] = {
        h.handle.lower(): str(h.profile_id) for h in all_history if h.handle
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

            # Check if any Instagram link/handle was provided
            if is_empty_or_placeholder(ig_link_cell) and is_empty_or_placeholder(ig_name_cell):
                if "instagram.com" not in yt_link_cell.lower():
                    # No IG channel provided in sheet -> Completely omit from Google Sync!
                    continue

            # Prioritize link column, else name column
            target_text = ig_link_cell if not is_empty_or_placeholder(ig_link_cell) else ig_name_cell
            if "instagram.com" in yt_link_cell.lower():
                target_text = f"{target_text}\n{yt_link_cell.strip()}"

            extracted_handles = extract_instagram_handles(target_text)

            # If ig_name has an extra specific handle
            if not is_empty_or_placeholder(ig_name_cell) and target_text != ig_name_cell:
                extra_handles = extract_instagram_handles(ig_name_cell)
                for eh in extra_handles:
                    if eh not in extracted_handles:
                        extracted_handles.append(eh)

            # If an Instagram link was attempted, but the format is broken / invalid -> Link Invalid
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

                # STEP 1: Database Check (Check Channel ID & Handle History first)
                pid = history_to_pid.get(handle)
                prof = profile_by_id.get(pid) if pid else None

                # Check if handle matches an existing Channel ID where the primary username is different
                if prof and prof.username and prof.username.lower() != handle:
                    # CASE 2: Handle Changed!
                    raw_items.append({
                        "channel_id": member_id,
                        "creator_name": creator_name,
                        "username": handle,
                        "old_username": prof.username,
                        "instagram_url": instagram_url,
                        "raw_input": ig_link_cell or handle,
                        "grade": tab["grade"],
                        "category": "Dedicated",
                        "tab_name": tab["name"],
                        "case_type": "HANDLE_CHANGED",
                        "status_label": "Handle Changed",
                        "status_color": "amber",
                        "can_add": False,
                    })
                    summary["handle_changed"] += 1
                elif handle in sp_by_username or (pid and pid in profile_by_id):
                    # Already tracked with matching handle
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

    # STEP 2: Verify candidate new channels live for deleted / invalid / valid / handle changed
    if candidate_handles_to_check:
        live_status_map = await check_handles_live_concurrent(list(candidate_handles_to_check))
    else:
        live_status_map = {}

    final_items: List[Dict[str, Any]] = []
    for item in raw_items:
        if item["case_type"] == "PENDING_CHECK":
            h = item["username"]
            res_obj = live_status_map.get(h, {"status": "VALID", "user_id": None, "username": None})
            st = res_obj.get("status", "VALID")
            user_id = res_obj.get("user_id")

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
                # Check if returned user.id belongs to an existing channel in DB under different handle
                matched_prof = profile_by_id.get(user_id) if user_id else None
                matched_sp = sp_by_ig_id.get(user_id) if user_id else None

                if matched_prof and matched_prof.username and matched_prof.username.lower() != h.lower():
                    item["case_type"] = "HANDLE_CHANGED"
                    item["status_label"] = "Handle Changed"
                    item["status_color"] = "amber"
                    item["old_username"] = matched_prof.username
                    item["can_add"] = False
                    summary["handle_changed"] += 1
                elif matched_sp and matched_sp.username and matched_sp.username.lower() != h.lower():
                    item["case_type"] = "HANDLE_CHANGED"
                    item["status_label"] = "Handle Changed"
                    item["status_color"] = "amber"
                    item["old_username"] = matched_sp.username
                    item["can_add"] = False
                    summary["handle_changed"] += 1
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
                "grade": item.get("grade", "Inactive"),
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
