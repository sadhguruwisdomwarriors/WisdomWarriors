import csv
import io
import logging
import re
import urllib.request
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
    "about", "help", "instagram", "https", "http", "www", "null", "undefined"
}


SENTENCE_SKIP_PHRASES = [
    "work in progress", "will share", "not created", "not yet",
    "don't have", "dont have", "not decided", "no channel", "no link",
    "not sure", "not applicable", "n/a"
]

def extract_instagram_handles(text_content: str) -> List[str]:
    """
    Extracts all valid Instagram handles from a string that may contain multiple links,
    handles, or freeform text across multiple lines or comma-separated values.
    """
    if not text_content:
        return []

    text_lower = text_content.lower().strip()
    if any(phrase in text_lower for phrase in SENTENCE_SKIP_PHRASES):
        return []

    text_content = text_content.replace("\\n", "\n").replace("\\r", "\r")
    handles = []

    # 1. Direct Regex for all Instagram URLs anywhere in the string
    for m in re.finditer(r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9._]+)', text_content, re.IGNORECASE):
        h = m.group(1).strip().rstrip('/')
        if h.lower() not in INVALID_TERMS and not h.lower().startswith("share"):
            handles.append(h.lstrip('@').lower())

    # 2. Extract @handles
    for m in re.finditer(r'@([a-zA-Z0-9._]+)', text_content):
        h = m.group(1).strip()
        if h.lower() not in INVALID_TERMS:
            handles.append(h.lstrip('@').lower())

    # 3. If no URLs or @handles were found, check if lines or comma-separated tokens are valid usernames
    if not handles:
        tokens = re.split(r'[\r\n,;|]+', text_content)
        for token in tokens:
            raw = token.strip().lstrip('@')
            if not raw or " " in raw or raw.startswith("http"):
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


async def analyze_google_sheets(db: AsyncSession) -> Dict[str, Any]:
    """
    Fetches Grade A-E tabs, parses single & multi-link cells, compares against database,
    and classifies every entry into Case 1 (Not Found), Case 2 (Handle Changed), or Case 3 (New Channel).
    """
    import asyncio
    
    scrape_profiles_res = await db.execute(select(ScrapeProfile))
    all_scrape_profiles = scrape_profiles_res.scalars().all()
    
    existing_handles_map: Dict[str, ScrapeProfile] = {
        p.username.lower(): p for p in all_scrape_profiles if p.username
    }

    items: List[Dict[str, Any]] = []
    summary = {
        "total_rows_scanned": 0,
        "new_channels": 0,
        "handle_changed": 0,
        "not_found": 0,
        "already_tracked": 0,
    }

    seen_channel_keys = set()
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
        col_other = 20

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
                    elif "other channels" in cell_clean or "different social media" in cell_clean:
                        col_other = idx
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
            other_cell = row[col_other].strip() if len(row) > col_other else ""
            yt_link_cell = row[col_yt_link].strip() if len(row) > col_yt_link else ""

            combined_ig_text = f"{ig_link_cell}\n{ig_name_cell}\n{other_cell}"
            if "instagram.com" in yt_link_cell:
                combined_ig_text += f"\n{yt_link_cell}"

            extracted_handles = extract_instagram_handles(combined_ig_text)

            # CASE 1: No valid Instagram handle found
            if not extracted_handles:
                raw_display = ig_link_cell or ig_name_cell or "No link provided"
                items.append({
                    "channel_id": member_id,
                    "creator_name": creator_name,
                    "username": "",
                    "instagram_url": "",
                    "raw_input": raw_display,
                    "grade": tab["grade"],
                    "category": "Dedicated",
                    "tab_name": tab["name"],
                    "case_type": "CHANNEL_NOT_FOUND",
                    "status_label": "Channel Not Found",
                    "status_color": "red",
                    "can_add": False,
                })
                summary["not_found"] += 1
                continue

            # CASE 2 / CASE 3 for each extracted handle
            for handle in extracted_handles:
                unique_key = f"{member_id}_{handle}"
                if unique_key in seen_channel_keys:
                    continue
                seen_channel_keys.add(unique_key)

                instagram_url = f"https://www.instagram.com/{handle}/"

                if handle in existing_handles_map:
                    items.append({
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
                    items.append({
                        "channel_id": member_id,
                        "creator_name": creator_name,
                        "username": handle,
                        "instagram_url": instagram_url,
                        "raw_input": ig_link_cell or handle,
                        "grade": tab["grade"],
                        "category": "Dedicated",
                        "tab_name": tab["name"],
                        "case_type": "NEW_CHANNEL",
                        "status_label": "New Channel",
                        "status_color": "green",
                        "can_add": True,
                    })
                    summary["new_channels"] += 1

    return {
        "summary": summary,
        "items": items,
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
