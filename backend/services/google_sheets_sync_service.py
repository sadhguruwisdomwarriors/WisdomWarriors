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
from sqlalchemy import select

from backend.models.scrape_profile import ScrapeProfile
from backend.models.profile import Profile
from backend.models.profile_handle_history import ProfileHandleHistory
from backend.repositories.scrape_profile_repo import add_scrape_profiles_bulk, update_scrape_profile_fields

logger = logging.getLogger(__name__)

DEDICATED_SPREADSHEET_ID = "1rF7tGOjn5gdEWnn3DEwao51wPvDIf2xLgD_WJk47xA0"
DEDICATED_TABS = [
    {"name": "Grade A", "gid": "0", "grade": "A"},
    {"name": "Grade B", "gid": "1853726635", "grade": "B"},
    {"name": "Grade C", "gid": "690782911", "grade": "C"},
    {"name": "Grade D", "gid": "859249885", "grade": "D"},
    {"name": "Grade E", "gid": "200360753", "grade": "E"},
    {"name": "Inactive", "gid": "157504391", "grade": "Inactive"},
]

IHI_SPREADSHEET_ID = "1J027IUUkk6wWvbactK6qgRwYUWoEafIxIScQwiDq1BU"
IHI_TABS = [
    {"name": "IHI Master", "gid": "1922340728", "grade": "IHI"},
]

INVALID_TERMS = {
    "na", "n/a", "nil", "none", "not created", "not yet", "not yet made",
    "work in progress", "don't have any", "dont have any", "no", "-", "--",
    "not decided yet", "reels", "p", "explore", "stories", "share", "tags",
    "about", "help", "instagram", "https", "http", "www", "null", "undefined",
    "reel", "tv", "profile", "user", "post", "posts", "youtube", "twitter",
    "linkedin", "facebook", "fb", "social", "media"
}

SKIP_PHRASES = {
    "na", "n/a", "nil", "none", "no", "no account", "dont have", "don't have",
    "does not have", "does not have (yet)", "not created", "not yet", "not yet made",
    "work in progress", "will share", "will share once ready", "not decided",
    "not decided yet", "no channel", "no link", "not sure", "not applicable",
    "-", "--", ".", "...", "", "no insta", "no instagram", "no insta account", "nil.",
    "yet to open a new page", "yet to open", "not yet opened", "creating new page",
    "new page", "no page", "nil (will create new account)", "will create new account",
    "yet to create channel", "in module 2", "i only have my personal ac",
    "i only have my personal ac.", "i do not have any social media accounts", "india and aligarh",
    "i'm creating new channel", "i am creating new channel", "creating new channel",
    "yet to create channel - in module 2", "no channel link", "no link available", "not available"
}

VERIFIED_DELETED_OR_INVALID = {
    "sadhgurujistory",
    "sadhguru_marathi_samvaad",
    "sourceofyoga",
    "adiyogi.chikkaballapura",
    "manraj_music",
    "wisdomwarriermanish",
    "sadhguru_vairagya",
    "sanathan_warriors",
    "english",
    "bazinganow",
    "regular",
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
    return any(cleaned == phrase or cleaned.startswith(phrase + " ") or cleaned.startswith(phrase + "(") or cleaned.startswith(phrase + " -") for phrase in SKIP_PHRASES)


def is_valid_ig_handle(h: str) -> bool:
    if not h or len(h) < 3 or len(h) > 30:
        return False
    clean = h.strip().lower().lstrip('@')
    if clean in INVALID_TERMS or clean.startswith("share"):
        return False
    if clean.isdigit() or not re.search(r'[a-zA-Z]', clean):
        return False
    return bool(re.match(r'^[a-zA-Z0-9._]{3,30}$', clean))


def extract_instagram_handles(text_content: str) -> List[str]:
    """
    STRICT Instagram-Only Extractor:
    1. Pre-cleans text by stripping non-Instagram URLs (YouTube, LinkedIn, Twitter/X, Facebook).
    2. Extracts handles exclusively from valid instagram.com URLs.
    3. If no Instagram URL is found, extracts from explicit @handle ONLY if the cell explicitly refers to Instagram.
    4. Never extracts from YouTube, LinkedIn, Twitter, or arbitrary freeform text.
    """
    if not text_content or is_empty_or_placeholder(text_content):
        return []

    text_content = text_content.replace("\\n", "\n").replace("\\r", "")

    # Strip out non-Instagram URLs completely
    cleaned_text = re.sub(
        r'https?:\/\/(?:www\.)?(?:youtube\.com|youtu\.be|linkedin\.com|twitter\.com|x\.com|facebook\.com|fb\.com)[^\s\n\r,;]*',
        ' ',
        text_content,
        flags=re.IGNORECASE
    )

    handles = []

    # Priority 1: Direct Regex for all Instagram URLs (e.g. instagram.com/{handle})
    for m in re.finditer(r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9._]+)', cleaned_text, re.IGNORECASE):
        h = m.group(1).strip().rstrip('/')
        if is_valid_ig_handle(h):
            handles.append(h.lstrip('@').lower())

    # Priority 2: If NO Instagram URL was found, check for explicit @handle only if cell mentions Instagram
    if not handles and ("instagram" in text_content.lower() or "insta" in text_content.lower()):
        for m in re.finditer(r'@([a-zA-Z0-9._]+)', cleaned_text):
            h = m.group(1).strip()
            if is_valid_ig_handle(h):
                handles.append(h.lstrip('@').lower())

    # Deduplicate preserving order
    seen = set()
    result = []
    for h in handles:
        if h not in seen:
            seen.add(h)
            result.append(h)
    return result


def fetch_tab_csv_sync(spreadsheet_id: str, gid: str) -> str:
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.read().decode("utf-8", errors="replace")


def check_instagram_handle_live_sync(handle: str) -> Dict[str, Any]:
    """
    Robust Reachability Verification:
    - Known deleted/invalid handles return DELETED immediately.
    - Live Instagram API check identifies 404s/deleted vs active accounts.
    """
    clean_h = handle.strip().lower().lstrip('@')
    if clean_h in VERIFIED_DELETED_OR_INVALID:
        return {"status": "DELETED", "user_id": None, "username": None}

    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={clean_h}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15",
            "x-ig-app-id": "936619743392459",
            "Sec-Fetch-Site": "same-origin",
        }
    )
    try:
        with urllib.request.urlopen(req, context=ssl_context, timeout=4) as response:
            data = json.loads(response.read().decode("utf-8"))
            user = data.get("data", {}).get("user")
            if user and user.get("id"):
                return {"status": "VALID", "user_id": str(user.get("id")), "username": user.get("username")}
            return {"status": "DELETED", "user_id": None, "username": None}
    except urllib.error.HTTPError as e:
        # STRICT: 404 / 410 is deleted
        if e.code in [404, 410]:
            return {"status": "DELETED", "user_id": None, "username": None}
        # 401, 400, 429 means active account challenged by anti-bot -> VALID
        return {"status": "VALID", "user_id": None, "username": clean_h}
    except urllib.error.URLError:
        return {"status": "INVALID", "user_id": None, "username": None}
    except Exception:
        return {"status": "VALID", "user_id": None, "username": clean_h}


async def check_handles_live_concurrent(handles: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Checks candidate handles concurrently with controlled concurrency (10 workers).
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


async def analyze_google_sheets(db: AsyncSession, source: str = "dedicated") -> Dict[str, Any]:
    """
    Parallel sync analyzer supporting both:
    1. "dedicated": Dedicated Master Database (Grades A-E & Inactive, Category: Dedicated)
    2. "ihi": IHI Master Database (In-house Influencers, Category: In-house influencer)
    """
    loop = asyncio.get_running_loop()
    source_lower = (source or "dedicated").strip().lower()

    if source_lower == "ihi":
        spreadsheet_id = IHI_SPREADSHEET_ID
        tabs = IHI_TABS
        default_category = "In-house influencer"
    else:
        spreadsheet_id = DEDICATED_SPREADSHEET_ID
        tabs = DEDICATED_TABS
        default_category = "Dedicated"

    # Step 1: Query DB tables
    scrape_profiles_res = await db.execute(select(ScrapeProfile))
    all_scrape_profiles = scrape_profiles_res.scalars().all()
    sp_by_username = {p.username.lower(): p for p in all_scrape_profiles if p.username}

    profiles_res = await db.execute(select(Profile))
    all_profiles = profiles_res.scalars().all()
    profile_by_id = {str(p.id): p for p in all_profiles if p.id}

    history_res = await db.execute(select(ProfileHandleHistory))
    all_history = history_res.scalars().all()
    history_to_pid = {h.handle.lower(): str(h.profile_id) for h in all_history if h.handle}

    # Step 2: Parallel fetch all tabs
    csv_tasks = [loop.run_in_executor(None, fetch_tab_csv_sync, spreadsheet_id, tab["gid"]) for tab in tabs]
    csv_results = await asyncio.gather(*csv_tasks, return_exceptions=True)

    raw_items: List[Dict[str, Any]] = []
    seen_channel_keys = set()
    candidate_handles_to_check = set()

    summary = {
        "total_rows_scanned": 0,
        "new_channels": 0,
        "handle_changed": 0,
        "link_invalid": 0,
        "channel_deleted": 0,
        "already_tracked": 0,
        "source": source_lower,
    }

    for idx, tab in enumerate(tabs):
        csv_text = csv_results[idx]
        if isinstance(csv_text, Exception) or not isinstance(csv_text, str):
            logger.error(f"Error fetching tab {tab['name']}: {csv_text}")
            continue

        reader = list(csv.reader(io.StringIO(csv_text)))
        header_idx = -1
        for i, row in enumerate(reader):
            row_str = " ".join(row).lower()
            if "name" in row_str or "channel" in row_str or "link" in row_str or "s.no" in row_str or "email" in row_str:
                header_idx = i
                break
        if header_idx == -1:
            header_idx = 0

        header = reader[header_idx]
        col_id = 0
        col_name = 1
        col_ig_name = -1
        col_ig_link = -1
        col_grade = -1

        for idx_c, cell in enumerate(header):
            cell_clean = cell.strip().lower()
            if cell_clean in ["id", "s.no"]:
                if cell_clean == "id":
                    col_id = idx_c
            elif "full name" in cell_clean or cell_clean == "name":
                col_name = idx_c
            elif "instagram channel name" in cell_clean:
                col_ig_name = idx_c
            elif "instagram channel link" in cell_clean or "channel links" in cell_clean or cell_clean == "links":
                col_ig_link = idx_c
            elif cell_clean == "grade":
                col_grade = idx_c

        for row in reader[header_idx+1:]:
            if not row or len(row) == 0:
                continue

            member_id = ""
            if len(row) > 0 and row[0].strip().upper().startswith("SWW"):
                member_id = row[0].strip()
            elif col_id >= 0 and len(row) > col_id and row[col_id].strip().upper().startswith("SWW"):
                member_id = row[col_id].strip()

            if not member_id:
                continue

            creator_name = row[col_name].strip() if (col_name >= 0 and len(row) > col_name) else ""
            ig_link_cell = row[col_ig_link].strip() if (col_ig_link >= 0 and len(row) > col_ig_link) else ""
            ig_name_cell = row[col_ig_name].strip() if (col_ig_name >= 0 and len(row) > col_ig_name) else ""
            
            row_grade = tab["grade"]
            if col_grade >= 0 and len(row) > col_grade and row[col_grade].strip():
                clean_grade = row[col_grade].strip()
                if clean_grade.upper() in ["A", "B", "C", "D", "E", "INACTIVE"]:
                    row_grade = "Inactive" if clean_grade.upper() == "INACTIVE" else clean_grade.upper()
                elif clean_grade:
                    row_grade = clean_grade

            # Check if any Instagram link/handle was provided
            if is_empty_or_placeholder(ig_link_cell) and is_empty_or_placeholder(ig_name_cell):
                continue

            target_text = ig_link_cell if not is_empty_or_placeholder(ig_link_cell) else ig_name_cell

            if is_empty_or_placeholder(target_text):
                continue

            extracted_handles = extract_instagram_handles(target_text)

            # If ig_name has an extra specific handle
            if not is_empty_or_placeholder(ig_name_cell) and target_text != ig_name_cell:
                for eh in extract_instagram_handles(ig_name_cell):
                    if eh not in extracted_handles:
                        extracted_handles.append(eh)

            if not extracted_handles:
                # If there's no Instagram link at all, skip non-Instagram rows
                if "instagram" in target_text.lower() or "insta" in target_text.lower():
                    raw_display = ig_link_cell or ig_name_cell or "Malformed link"
                    raw_items.append({
                        "channel_id": member_id,
                        "creator_name": creator_name,
                        "username": "",
                        "instagram_url": "",
                        "raw_input": raw_display,
                        "grade": row_grade,
                        "category": default_category,
                        "tab_name": tab["name"],
                        "case_type": "LINK_INVALID",
                        "status_label": "Link Invalid",
                        "status_color": "red",
                        "can_add": False,
                    })
                    summary["link_invalid"] += 1
                continue

            summary["total_rows_scanned"] += 1

            for handle in extracted_handles:
                unique_key = f"{member_id}_{handle}"
                if unique_key in seen_channel_keys:
                    continue
                seen_channel_keys.add(unique_key)

                instagram_url = f"https://www.instagram.com/{handle}/"

                # Check Channel ID / Profile History first
                pid = history_to_pid.get(handle)
                prof = profile_by_id.get(pid) if pid else None

                if prof and prof.username and prof.username.lower() != handle:
                    raw_items.append({
                        "channel_id": member_id,
                        "creator_name": creator_name,
                        "username": handle,
                        "old_username": prof.username,
                        "instagram_url": instagram_url,
                        "raw_input": ig_link_cell or handle,
                        "grade": row_grade,
                        "category": default_category,
                        "tab_name": tab["name"],
                        "case_type": "HANDLE_CHANGED",
                        "status_label": "Handle Changed",
                        "status_color": "amber",
                        "can_add": False,
                    })
                    summary["handle_changed"] += 1
                elif handle in sp_by_username or (pid and pid in profile_by_id):
                    raw_items.append({
                        "channel_id": member_id,
                        "creator_name": creator_name,
                        "username": handle,
                        "instagram_url": instagram_url,
                        "raw_input": ig_link_cell or handle,
                        "grade": row_grade,
                        "category": default_category,
                        "tab_name": tab["name"],
                        "case_type": "ALREADY_TRACKED",
                        "status_label": "Already Tracked",
                        "status_color": "gray",
                        "can_add": False,
                    })
                    summary["already_tracked"] += 1
                else:
                    candidate_handles_to_check.add(handle)
                    raw_items.append({
                        "channel_id": member_id,
                        "creator_name": creator_name,
                        "username": handle,
                        "instagram_url": instagram_url,
                        "raw_input": ig_link_cell or handle,
                        "grade": row_grade,
                        "category": default_category,
                        "tab_name": tab["name"],
                        "case_type": "PENDING_CHECK",
                        "status_label": "Checking...",
                        "status_color": "green",
                        "can_add": True,
                    })

    # Step 3: Fast concurrent verification of candidate handles
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
                matched_prof = profile_by_id.get(user_id) if user_id else None

                if matched_prof and matched_prof.username and matched_prof.username.lower() != h.lower():
                    item["case_type"] = "HANDLE_CHANGED"
                    item["status_label"] = "Handle Changed"
                    item["status_color"] = "amber"
                    item["old_username"] = matched_prof.username
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
