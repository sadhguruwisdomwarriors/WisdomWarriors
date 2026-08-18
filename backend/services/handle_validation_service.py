import asyncio
import logging
import re
from functools import partial
from typing import Any, TypedDict
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.repositories import profile_repo
from backend.services.apify.normalizer import normalize_profile
from backend.services.apify.profiles_runner import run_profiles_actor

logger = logging.getLogger(__name__)


class HandleValidationResultItem(TypedDict):
    submitted_handle: str
    normalized_handle: str
    status: str             # "FOUND" | "NOT_FOUND" | "ERROR"
    instagram_id: str | None
    current_handle: str | None
    source: str | None       # "database" | "apify_lookup" | None
    instagram_url: str
    error_message: str | None


class HandleValidationResponse(TypedDict):
    total: int
    found_count: int
    not_found_count: int
    error_count: int
    results: list[HandleValidationResultItem]


def normalize_input_handle(raw_handle: str) -> str:
    cleaned = (raw_handle or "").strip().lstrip("@").rstrip("/")
    cleaned = re.sub(r"\?.*$", "", cleaned)
    if not cleaned:
        return ""
    if "/" in cleaned:
        cleaned = cleaned.split("/")[-1]
    return cleaned.strip()


async def validate_and_resolve_handles(
    db: AsyncSession,
    handles: list[str],
    apify_token: str | None = None,
) -> HandleValidationResponse:
    results_by_handle: dict[str, HandleValidationResultItem] = {}
    normalized_to_submitted: dict[str, str] = {}
    unresolved_handles: list[str] = []

    # Step 1: Normalize handles and remove duplicate inputs
    for raw in handles:
        norm = normalize_input_handle(raw)
        if not norm:
            continue
        lower_key = norm.lower()
        if lower_key not in normalized_to_submitted:
            normalized_to_submitted[lower_key] = norm

    distinct_handles = list(normalized_to_submitted.values())

    # Step 2: Search Database First
    for norm_handle in distinct_handles:
        lower_key = norm_handle.lower()
        existing_profile = await profile_repo.get_profile_by_handle_or_history(db, norm_handle)
        
        if existing_profile is not None and existing_profile.id:
            # Case A: Found in DB with valid Instagram ID
            display_handle = existing_profile.username or norm_handle
            results_by_handle[lower_key] = {
                "submitted_handle": norm_handle,
                "normalized_handle": norm_handle,
                "status": "FOUND",
                "instagram_id": str(existing_profile.id),
                "current_handle": display_handle,
                "source": "database",
                "instagram_url": f"https://instagram.com/{display_handle}",
                "error_message": None,
            }
            # Record handle mapping in history
            await profile_repo.record_handle_history(db, existing_profile.id, norm_handle)
        else:
            # Case B / C: Missing in DB or missing Instagram ID -> Queue for Apify lookup
            unresolved_handles.append(norm_handle)

    # Step 3: For unresolved handles, attempt Apify profile lookup
    if unresolved_handles:
        logger.info("Resolving %d handles via Apify lookup", len(unresolved_handles))
        try:
            apify_result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    partial(run_profiles_actor, unresolved_handles, apify_token),
                ),
                timeout=max(60, int(get_settings().apify_actor_timeout_seconds)),
            )

            raw_items = apify_result[0] if isinstance(apify_result, tuple) else apify_result
            fetched_by_username: dict[str, dict[str, Any]] = {}

            for raw in raw_items:
                norm_prof = normalize_profile(raw)
                username = normalize_input_handle(norm_prof.get("username", ""))
                if username:
                    fetched_by_username[username.lower()] = norm_prof

            for norm_handle in unresolved_handles:
                lower_key = norm_handle.lower()
                norm_prof = fetched_by_username.get(lower_key)

                if norm_prof and norm_prof.get("id") and norm_prof.get("username"):
                    # Successfully resolved via Apify!
                    profile = await profile_repo.upsert_profile(db, norm_prof)
                    await profile_repo.record_handle_history(db, profile.id, norm_handle)
                    await profile_repo.record_handle_history(db, profile.id, profile.username)

                    display_handle = profile.username or norm_handle
                    results_by_handle[lower_key] = {
                        "submitted_handle": norm_handle,
                        "normalized_handle": norm_handle,
                        "status": "FOUND",
                        "instagram_id": str(profile.id),
                        "current_handle": display_handle,
                        "source": "apify_lookup",
                        "instagram_url": f"https://instagram.com/{display_handle}",
                        "error_message": None,
                    }
                else:
                    # Account non-existent or ID not found
                    results_by_handle[lower_key] = {
                        "submitted_handle": norm_handle,
                        "normalized_handle": norm_handle,
                        "status": "NOT_FOUND",
                        "instagram_id": None,
                        "current_handle": None,
                        "source": None,
                        "instagram_url": f"https://instagram.com/{norm_handle}",
                        "error_message": "Instagram ID could not be resolved.",
                    }

        except Exception as exc:
            logger.warning("Apify profile lookup failed: %s", exc, exc_info=True)
            for norm_handle in unresolved_handles:
                lower_key = norm_handle.lower()
                if lower_key not in results_by_handle:
                    results_by_handle[lower_key] = {
                        "submitted_handle": norm_handle,
                        "normalized_handle": norm_handle,
                        "status": "ERROR",
                        "instagram_id": None,
                        "current_handle": None,
                        "source": None,
                        "instagram_url": f"https://instagram.com/{norm_handle}",
                        "error_message": f"Lookup error: {str(exc)}",
                    }

    await db.commit()

    results_list: list[HandleValidationResultItem] = list(results_by_handle.values())
    found_count = sum(1 for item in results_list if item["status"] == "FOUND")
    not_found_count = sum(1 for item in results_list if item["status"] == "NOT_FOUND")
    error_count = sum(1 for item in results_list if item["status"] == "ERROR")

    return {
        "total": len(results_list),
        "found_count": found_count,
        "not_found_count": not_found_count,
        "error_count": error_count,
        "results": results_list,
    }
