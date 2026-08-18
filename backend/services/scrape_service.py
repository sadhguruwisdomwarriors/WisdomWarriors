import asyncio
import hashlib
import json
import logging
import os
import random
from pathlib import Path
from datetime import date, datetime, timezone
from functools import partial
from typing import Any

logger = logging.getLogger(__name__)

_TERMINAL_FAILURE_HINTS = (
    "no profile data returned",
    "not found",
    "private",
    "invalid",
    "username does not exist",
)

from sqlalchemy import delete, func, select

from backend.db.engine import AsyncSessionLocal
from backend.models.post_snapshot import PostSnapshot
from backend.models.post_snapshot_hashtag import PostSnapshotHashtag
from backend.models.post_snapshot_mention import PostSnapshotMention
from backend.models.post_snapshot_tagged_user import PostSnapshotTaggedUser
from backend.models.profile import Profile
from backend.models.profile_snapshot import ProfileSnapshot
from backend.models.scrape_run import ScrapeRun
from backend.models.scrape_profile import ScrapeProfile
from backend.models.scrape_run_profile_progress import ScrapeRunProfileProgress
from backend.repositories import post_repo, profile_repo, scrape_run_repo
from backend.services.apify.normalizer import normalize_post, normalize_profile
from backend.services.apify.posts_runner import run_posts_actor
from backend.services.apify.profiles_runner import run_profiles_actor
from backend.config import get_settings
from backend.services.embedding.indexer import embed_and_index_posts, embed_and_index_profiles
from backend.services.scheduler.period import derive_period_label
from backend.services.storage import upload_display_image_to_supabase, upload_profile_image_to_supabase


_RESUME_TASKS: set[asyncio.Task[Any]] = set()


def _normalize_username_key(username: str) -> str:
    return (username or "").strip().lstrip("@").lower()


def _is_terminal_profile_error(error_message: str | None) -> bool:
    message = (error_message or "").strip().lower()
    if not message:
        return False
    return any(hint in message for hint in _TERMINAL_FAILURE_HINTS)


def _clean_usernames(usernames: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for username in usernames:
        normalized = _normalize_username_key(username)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


async def _delete_posts_for_username_in_run(db, run_id: int, username: str) -> None:
    owner_key = _normalize_username_key(username)
    await db.execute(
        delete(PostSnapshotTaggedUser)
        .where(PostSnapshotTaggedUser.run_id == run_id)
        .where(func.lower(PostSnapshotTaggedUser.owner_username) == owner_key)
    )
    await db.execute(
        delete(PostSnapshotMention)
        .where(PostSnapshotMention.run_id == run_id)
        .where(func.lower(PostSnapshotMention.owner_username) == owner_key)
    )
    await db.execute(
        delete(PostSnapshotHashtag)
        .where(PostSnapshotHashtag.run_id == run_id)
        .where(func.lower(PostSnapshotHashtag.owner_username) == owner_key)
    )
    await db.execute(
        delete(PostSnapshot)
        .where(PostSnapshot.run_id == run_id)
        .where(func.lower(PostSnapshot.owner_username) == owner_key)
    )


async def _delete_profile_snapshot_for_run(db, run_id: int, profile_id: str) -> None:
    await db.execute(
        delete(ProfileSnapshot)
        .where(ProfileSnapshot.run_id == run_id)
        .where(ProfileSnapshot.profile_id == profile_id)
    )


def _track_resume_task(task: asyncio.Task[Any]) -> None:
    _RESUME_TASKS.add(task)

    def _on_done(done_task: asyncio.Task[Any]) -> None:
        _RESUME_TASKS.discard(done_task)
        try:
            done_task.result()
        except Exception:
            logger.exception("Auto-resume task failed")

    task.add_done_callback(_on_done)


def build_posts_resume_payload(
    usernames: list[str],
    trigger: str,
    schedule_id: int | None,
    results_limit: int,
    only_posts_newer_than: str | None,
    date_from: str | None,
    date_to: str | None,
    frequency: str,
    data_detail_level: str,
    batch_mode: bool,
    enable_embeddings: bool,
    apify_token: str | None,
) -> str:
    payload = {
        "type": "posts",
        "usernames": usernames,
        "trigger": trigger,
        "schedule_id": schedule_id,
        "results_limit": results_limit,
        "only_posts_newer_than": only_posts_newer_than,
        "date_from": date_from,
        "date_to": date_to,
        "frequency": frequency,
        "data_detail_level": data_detail_level,
        "batch_mode": batch_mode,
        "enable_embeddings": enable_embeddings,
        "apify_token": apify_token,
    }
    return json.dumps(payload)


def build_profiles_resume_payload(
    usernames: list[str],
    trigger: str,
    schedule_id: int | None,
    frequency: str,
    batch_mode: bool,
    enable_embeddings: bool,
    apify_token: str | None,
) -> str:
    payload = {
        "type": "profiles",
        "usernames": usernames,
        "trigger": trigger,
        "schedule_id": schedule_id,
        "frequency": frequency,
        "batch_mode": batch_mode,
        "enable_embeddings": enable_embeddings,
        "apify_token": apify_token,
    }
    return json.dumps(payload)


def build_combined_resume_payload(
    usernames: list[str],
    trigger: str,
    schedule_id: int | None,
    frequency: str,
    results_limit: int,
    only_posts_newer_than: str | None,
    date_from: str | None,
    date_to: str | None,
    data_detail_level: str,
    batch_mode: bool,
    enable_embeddings: bool,
    apify_token: str | None,
) -> str:
    payload = {
        "type": "combined",
        "usernames": usernames,
        "trigger": trigger,
        "schedule_id": schedule_id,
        "frequency": frequency,
        "results_limit": results_limit,
        "only_posts_newer_than": only_posts_newer_than,
        "date_from": date_from,
        "date_to": date_to,
        "data_detail_level": data_detail_level,
        "batch_mode": batch_mode,
        "enable_embeddings": enable_embeddings,
        "apify_token": apify_token,
    }
    return json.dumps(payload)


def _parse_resume_payload(raw_payload: str | None) -> dict[str, Any]:
    if not raw_payload:
        return {}
    try:
        payload = json.loads(raw_payload)
        return payload if isinstance(payload, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


async def _delete_run_artifacts(db, run_id: int) -> None:
    # Remove partial run artifacts before retrying so resumed runs do not duplicate rows.
    await db.execute(delete(PostSnapshotTaggedUser).where(PostSnapshotTaggedUser.run_id == run_id))
    await db.execute(delete(PostSnapshotMention).where(PostSnapshotMention.run_id == run_id))
    await db.execute(delete(PostSnapshotHashtag).where(PostSnapshotHashtag.run_id == run_id))
    await db.execute(delete(PostSnapshot).where(PostSnapshot.run_id == run_id))
    await db.execute(delete(ProfileSnapshot).where(ProfileSnapshot.run_id == run_id))


async def _resume_run(run_id: int) -> None:
    async with AsyncSessionLocal() as db:
        run = await db.get(ScrapeRun, run_id)
        if run is None:
            return
        fallback_scraper_type = run.scraper_type
        fallback_trigger = run.trigger
        payload = _parse_resume_payload(run.resume_payload)
        usernames = payload.get("usernames")
        if not isinstance(usernames, list) or not usernames:
            scrape_profiles_result = await db.execute(select(ScrapeProfile).order_by(ScrapeProfile.position, ScrapeProfile.id))
            usernames = [row.username for row in scrape_profiles_result.scalars().all()]
        usernames = _clean_usernames([str(username) for username in usernames])

        await _append_run_log(db, run.id, "Server restarted; resuming scrape run from persisted settings.")
        await scrape_run_repo.mark_running_profiles_failed(
            db,
            run.id,
            "Server restarted while profile was processing. Profile will be retried.",
        )
        await scrape_run_repo.update_run(db, run.id, {
            "status": "running",
            "finished_at": None,
            "error_message": None,
            "embedding_error_message": None,
        })
        await db.commit()

    run_type = str(payload.get("type") or fallback_scraper_type or "").strip().lower()
    trigger = str(payload.get("trigger") or fallback_trigger or "manual")
    schedule_id = payload.get("schedule_id")

    if run_type == "profiles":
        await run_profiles_scrape(
            usernames=usernames,
            trigger=trigger,
            schedule_id=schedule_id,
            frequency=str(payload.get("frequency") or "on_demand"),
            shared_scraped_at=None,
            batch_mode=bool(payload.get("batch_mode", False)),
            enable_embeddings=bool(payload.get("enable_embeddings", True)),
            existing_run_id=run_id,
            finalize_run=True,
            apify_token=payload.get("apify_token"),
        )
        return

    if run_type == "combined":
        await run_combined_scrape(
            usernames=usernames,
            results_limit=int(payload.get("results_limit") or 100),
            only_posts_newer_than=payload.get("only_posts_newer_than"),
            date_from=payload.get("date_from"),
            date_to=payload.get("date_to"),
            data_detail_level=str(payload.get("data_detail_level") or "basicData"),
            enable_embeddings=bool(payload.get("enable_embeddings", True)),
            batch_mode=bool(payload.get("batch_mode", False)),
            trigger=trigger,
            schedule_id=schedule_id,
            frequency=str(payload.get("frequency") or "on_demand"),
            combined_run_id=run_id,
            apify_token=payload.get("apify_token"),
        )
        return

    await run_posts_scrape(
        usernames=usernames,
        scraper_type="posts",
        trigger=trigger,
        schedule_id=schedule_id,
        results_limit=int(payload.get("results_limit") or 100),
        only_posts_newer_than=payload.get("only_posts_newer_than"),
        date_from=payload.get("date_from"),
        date_to=payload.get("date_to"),
        frequency=str(payload.get("frequency") or "on_demand"),
        data_detail_level=str(payload.get("data_detail_level") or "basicData"),
        shared_scraped_at=None,
        enable_embeddings=bool(payload.get("enable_embeddings", True)),
        batch_mode=bool(payload.get("batch_mode", False)),
        existing_run_id=run_id,
        finalize_run=True,
        apify_token=payload.get("apify_token"),
    )


async def resume_incomplete_runs_on_startup() -> int:
    async with AsyncSessionLocal() as db:
        runs = await scrape_run_repo.claim_incomplete_runs_for_resume(db)
        await db.commit()

    for run in runs:
        task = asyncio.create_task(_resume_run(run.id), name=f"resume-scrape-run-{run.id}")
        _track_resume_task(task)
    return len(runs)


def _post_id(url: str, period_label: str) -> str:
    return hashlib.sha256(f"{url}:{period_label}".encode()).hexdigest()[:32]


def _is_supabase_storage_url(url: str | None) -> bool:
    settings = get_settings()
    if not url or not settings.supabase_url:
        return False
    public_prefix = f"{settings.supabase_url.rstrip('/')}/storage/v1/object/public/"
    return url.startswith(public_prefix)


async def _purge_ignored_instagram_account(db) -> None:
    ignored_usernames = ("instagram", "@instagram")

    profile_ids_result = await db.execute(
        select(Profile.id).where(func.lower(Profile.username).in_(ignored_usernames))
    )
    profile_ids = [row[0] for row in profile_ids_result.all()]

    await db.execute(
        delete(ScrapeProfile).where(func.lower(ScrapeProfile.username).in_(ignored_usernames))
    )
    await db.execute(
        delete(PostSnapshot).where(func.lower(PostSnapshot.owner_username).in_(ignored_usernames))
    )

    if profile_ids:
        await db.execute(delete(ProfileSnapshot).where(ProfileSnapshot.profile_id.in_(profile_ids)))
        await db.execute(delete(Profile).where(Profile.id.in_(profile_ids)))

    await db.commit()


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _is_timestamp_within_range(timestamp: datetime | None, date_from: str | None, date_to: str | None) -> bool:
    start = _parse_iso_date(date_from)
    end = _parse_iso_date(date_to)

    if start is None and end is None:
        return True
    if timestamp is None:
        return False

    post_date = timestamp.date()
    if start is not None and post_date < start:
        return False
    if end is not None and post_date > end:
        return False
    return True


_DEBUG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "debug_output")


def _dump_posts_debug(run_id: int, usernames: list[str], raw_items: list[dict]) -> None:
    """Write raw + normalized post data to debug_output/posts_run_<id>.json for DB verification."""
    os.makedirs(_DEBUG_DIR, exist_ok=True)
    normalised = []
    error_items = 0
    valid_items = 0
    for raw in raw_items:
        if raw.get("error"):
            error_items += 1
        norm = normalize_post(raw)
        if norm.get("url"):
            valid_items += 1
        normalised.append({k: str(v) if hasattr(v, "isoformat") else v for k, v in norm.items()})
    payload = {
        "run_id": run_id,
        "usernames": usernames,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "total_items": len(raw_items),
        "valid_items": valid_items,
        "error_items": error_items,
        "raw": raw_items,
        "normalized": normalised,
    }
    path = os.path.join(_DEBUG_DIR, f"posts_run_{run_id}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)


def _load_json_log_lines(raw_logs: str | None) -> list[str]:
    if not raw_logs:
        return []
    try:
        loaded = json.loads(raw_logs)
        return [line for line in loaded if isinstance(line, str)]
    except (json.JSONDecodeError, TypeError):
        return []


async def _append_run_log(db, run_id: int, message: str) -> None:
    run = await db.get(ScrapeRun, run_id)
    if run is None:
        return
    lines = _load_json_log_lines(run.raw_logs)
    lines.append(message)
    run.raw_logs = json.dumps(lines)
    await db.flush()


async def _extend_run_logs(db, run_id: int, messages: list[str]) -> None:
    if not messages:
        return
    run = await db.get(ScrapeRun, run_id)
    if run is None:
        return
    lines = _load_json_log_lines(run.raw_logs)
    lines.extend([message for message in messages if isinstance(message, str)])
    run.raw_logs = json.dumps(lines)
    await db.flush()


async def run_posts_scrape(
    usernames: list[str],
    scraper_type: str = "posts",
    trigger: str = "manual",
    schedule_id: int | None = None,
    results_limit: int = 100,
    only_posts_newer_than: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    frequency: str = "on_demand",
    data_detail_level: str = "basicData",
    shared_scraped_at: datetime | None = None,
    enable_embeddings: bool = True,
    batch_mode: bool = False,
    existing_run_id: int | None = None,
    finalize_run: bool = True,
    apify_token: str | None = None,
) -> int:
    resume_payload = build_posts_resume_payload(
        usernames=usernames,
        trigger=trigger,
        schedule_id=schedule_id,
        results_limit=results_limit,
        only_posts_newer_than=only_posts_newer_than,
        date_from=date_from,
        date_to=date_to,
        frequency=frequency,
        data_detail_level=data_detail_level,
        batch_mode=batch_mode,
        enable_embeddings=enable_embeddings,
        apify_token=apify_token,
    )
    async with AsyncSessionLocal() as db:
        settings = get_settings()
        await _purge_ignored_instagram_account(db)
        requested_usernames = _clean_usernames(usernames)
        initial_items_fetched = 0
        if existing_run_id is not None:
            run = await db.get(ScrapeRun, existing_run_id)
            if run is None:
                raise ValueError(f"Run {existing_run_id} not found")
            initial_items_fetched = 0 if run.scraper_type == "combined" else int(run.items_fetched or 0)
            await scrape_run_repo.update_run(db, run.id, {
                "status": "running",
                "finished_at": None,
                "embedding_status": "pending" if enable_embeddings else "skipped",
                "profiles_requested": len(requested_usernames),
                "error_message": None,
                "embedding_error_message": None,
                "resume_payload": resume_payload,
                "items_fetched": initial_items_fetched,
            })
        else:
            run = await scrape_run_repo.create_run(db, {
                "scraper_type": scraper_type,
                "trigger": trigger,
                "schedule_id": schedule_id,
                "embedding_status": "pending" if enable_embeddings else "skipped",
                "profiles_requested": len(requested_usernames),
                "resume_payload": resume_payload,
                "items_fetched": 0,
            })
            initial_items_fetched = 0

        await scrape_run_repo.initialize_profile_progress(db, run.id, requested_usernames)
        target_usernames = await scrape_run_repo.get_usernames_for_resume(
            db,
            run.id,
            settings.scrape_resume_max_attempts,
        )
        scraped_at = shared_scraped_at or datetime.now(timezone.utc)
        period_label = derive_period_label(frequency)
        fetched = initial_items_fetched
        embedding_status = "pending" if enable_embeddings else "skipped"
        embedding_error_message: str | None = None

        async def _fetch_posts_for_username(username: str):
            return await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    partial(run_posts_actor, [username], results_limit, only_posts_newer_than, data_detail_level, apify_token),
                ),
                timeout=max(60, int(get_settings().apify_actor_timeout_seconds)),
            )

        try:
            await _append_run_log(db, run.id, f"Posts stage started for {len(target_usernames)} pending/failed profile(s).")
            if date_from or date_to:
                requested_window = f"{date_from or 'any'} -> {date_to or 'any'}"
                await _append_run_log(db, run.id, f"Posts stage date filter applied: {requested_window}.")
            await db.commit()

            for username in target_usernames:
                current_progress_result = await db.execute(
                    select(ScrapeRunProfileProgress)
                    .where(ScrapeRunProfileProgress.run_id == run.id)
                    .where(ScrapeRunProfileProgress.username == _normalize_username_key(username))
                    .limit(1)
                )
                current_progress = current_progress_result.scalar_one_or_none()
                already_attempted = int(current_progress.attempt_count or 0) if current_progress else 0
                max_attempts = max(1, int(settings.scrape_resume_max_attempts or 1))
                if current_progress is not None and current_progress.status == "failed" and _is_terminal_profile_error(current_progress.error_message):
                    await _append_run_log(
                        db,
                        run.id,
                        f"Posts stage: skipping @{username} (terminal failure: {current_progress.error_message or 'unknown'}).",
                    )
                    await db.commit()
                    continue
                remaining_attempts = max(1, max_attempts - already_attempted)

                for attempt_index in range(remaining_attempts):
                    attempt_no = already_attempted + attempt_index + 1
                    await scrape_run_repo.mark_profile_running(db, run.id, username)
                    await _append_run_log(
                        db,
                        run.id,
                        f"Posts stage: scraping @{username} (attempt {attempt_no}/{max_attempts})...",
                    )
                    await db.commit()

                    try:
                        result = await _fetch_posts_for_username(username)
                        apify_metadata: dict[str, Any] = {}
                        if isinstance(result, tuple):
                            if len(result) >= 3:
                                raw_items, raw_logs, apify_metadata = result[0], result[1], result[2] or {}
                            else:
                                raw_items, raw_logs = result[0], result[1]
                        else:
                            raw_items, raw_logs = result, []

                        if apify_metadata:
                            await scrape_run_repo.update_apify_stage_metadata(
                                db,
                                run.id,
                                stage="posts",
                                metadata=apify_metadata,
                                event_type="actor_call",
                                extra={
                                    "username": _normalize_username_key(username),
                                    "attempt": attempt_no,
                                },
                            )

                        if raw_logs:
                            await _extend_run_logs(db, run.id, raw_logs)

                        await _delete_posts_for_username_in_run(db, run.id, username)
                        profile_fetched = 0
                        debug_items: list[dict[str, Any]] = []

                        for raw in raw_items:
                            norm = normalize_post(raw)
                            url = norm.get("url", "")
                            if not url:
                                continue
                            if not _is_timestamp_within_range(norm.get("timestamp"), date_from, date_to):
                                continue

                            owner_username = _normalize_username_key(norm.get("owner_username") or username)
                            target_username = _normalize_username_key(username)

                            # Keep post if target channel is owner OR a collaborator
                            participants = [owner_username]
                            coauthors_raw = norm.get("coauthor_producers") or []
                            for coauthor in coauthors_raw:
                                if isinstance(coauthor, str):
                                    participants.append(_normalize_username_key(coauthor))
                                elif isinstance(coauthor, dict):
                                    for key in ("username", "userName", "ownerUsername", "handle"):
                                        val = coauthor.get(key)
                                        if isinstance(val, str) and val.strip():
                                            participants.append(_normalize_username_key(val))
                                            break

                            if target_username not in participants:
                                continue

                            norm["owner_username"] = owner_username
                            norm["id"] = _post_id(url, period_label)

                            display_url = norm.get("display_url")
                            if display_url:
                                try:
                                    upload_result = await asyncio.get_event_loop().run_in_executor(
                                        None,
                                        partial(upload_display_image_to_supabase, display_url, run.id, norm["id"]),
                                    )
                                    if upload_result:
                                        norm["display_storage_path"] = upload_result.path
                                        norm["display_storage_url"] = upload_result.public_url
                                except Exception:
                                    logger.warning("Storage upload failed for post %s", norm["id"], exc_info=True)

                            norm["period_label"] = period_label
                            norm["scraped_at"] = scraped_at
                            norm["run_id"] = run.id
                            snap = await post_repo.insert_snapshot(db, {
                                "post_id": norm["id"],
                                "run_id": run.id,
                                "owner_username": owner_username,
                                "url": norm["url"],
                                "timestamp": norm.get("timestamp"),
                                "likes_count": norm.get("likes_count", 0) or 0,
                                "video_play_count": norm.get("video_play_count", 0) or 0,
                                "type": norm.get("type"),
                                "video_url": norm.get("video_url"),
                                "display_url": norm.get("display_url"),
                                "display_storage_path": norm.get("display_storage_path"),
                                "display_storage_url": norm.get("display_storage_url"),
                                "caption": norm.get("caption"),
                                "product_type": norm.get("product_type"),
                                "input_url": norm.get("input_url"),
                                "hashtags": norm.get("hashtags") or [],
                                "mentions": norm.get("mentions") or [],
                                "tagged_users": norm.get("tagged_users") or [],
                                "coauthor_producers": norm.get("coauthor_producers") or [],
                                "period_label": period_label,
                                "scraped_at": scraped_at,
                            })
                            await post_repo.replace_snapshot_hashtags(
                                db,
                                snapshot_id=snap.id,
                                post_id=norm["id"],
                                run_id=run.id,
                                period_label=period_label,
                                owner_username=owner_username,
                                hashtags=norm.get("hashtags") or [],
                            )
                            await post_repo.replace_snapshot_mentions(
                                db,
                                snapshot_id=snap.id,
                                post_id=norm["id"],
                                run_id=run.id,
                                period_label=period_label,
                                owner_username=owner_username,
                                mentions=norm.get("mentions") or [],
                            )
                            await post_repo.replace_snapshot_tagged_users(
                                db,
                                snapshot_id=snap.id,
                                post_id=norm["id"],
                                run_id=run.id,
                                period_label=period_label,
                                owner_username=owner_username,
                                tagged_users=norm.get("tagged_users") or [],
                            )
                            profile_fetched += 1
                            debug_items.append(raw)

                        if debug_items:
                            _dump_posts_debug(run.id, [username], debug_items)

                        fetched += profile_fetched
                        await scrape_run_repo.mark_profile_success(db, run.id, username, profile_fetched)
                        await scrape_run_repo.update_run(db, run.id, {"items_fetched": fetched})
                        if profile_fetched == 0:
                            await _append_run_log(db, run.id, f"Posts stage: @{username} scraped with 0 posts.")
                        else:
                            await _append_run_log(db, run.id, f"Posts stage: @{username} persisted {profile_fetched} post(s).")
                        await db.commit()
                        break
                    except Exception as exc:
                        logger.warning("Posts scrape failed for %s", username, exc_info=exc)
                        await scrape_run_repo.mark_profile_failed(db, run.id, username, str(exc))
                        await scrape_run_repo.update_run(db, run.id, {"items_fetched": fetched})

                        terminal_failure = _is_terminal_profile_error(str(exc))
                        has_more_attempts = (attempt_index < (remaining_attempts - 1)) and not terminal_failure
                        if has_more_attempts:
                            backoff_base = max(1, int(settings.scrape_retry_backoff_base_seconds or 1))
                            backoff_cap = max(backoff_base, int(settings.scrape_retry_backoff_max_seconds or backoff_base))
                            retry_delay = min(backoff_cap, backoff_base * (2 ** attempt_index))
                            jitter = random.uniform(0, retry_delay * 0.25)
                            wait_seconds = retry_delay + jitter
                            await _append_run_log(
                                db,
                                run.id,
                                f"Posts stage failed for @{username}: {exc}. Retrying in {wait_seconds:.1f}s...",
                            )
                            await db.commit()
                            await asyncio.sleep(wait_seconds)
                        else:
                            terminal_note = " Marked terminal (non-retryable)." if terminal_failure else " Retry budget exhausted."
                            await _append_run_log(
                                db,
                                run.id,
                                f"Posts stage failed for @{username}: {exc}.{terminal_note}",
                            )
                            await db.commit()

            rows = await scrape_run_repo.get_profile_progress_rows(db, run.id)
            failed_count = len([row for row in rows if row.status == "failed"])
            pending_count = len([row for row in rows if row.status == "pending"])
            running_count = len([row for row in rows if row.status == "running"])
            unresolved_count = failed_count + pending_count + running_count

            if not enable_embeddings:
                embedding_status = "skipped"
            elif fetched == 0:
                embedding_status = "skipped"
            else:
                await db.refresh(run)
                if run.embedding_status == "skipped":
                    embedding_status = "skipped"
                else:
                    try:
                        await _append_run_log(db, run.id, "Posts stage: generating embeddings...")
                        await db.commit()
                        await embed_and_index_posts(db, period_label)
                        embedding_status = "completed"
                    except Exception as exc:
                        embedding_status = "failed"
                        embedding_error_message = str(exc)

            status_update = {
                "embedding_status": embedding_status,
                "items_fetched": fetched,
                "embedding_error_message": embedding_error_message,
            }
            if finalize_run:
                if unresolved_count:
                    status_update.update({
                        "status": "failed",
                        "finished_at": datetime.now(timezone.utc),
                        "error_message": (
                            "Posts stage completed with unresolved profiles: "
                            f"failed={failed_count}, pending={pending_count}, running={running_count}."
                        ),
                    })
                    await _append_run_log(
                        db,
                        run.id,
                        (
                            "Posts stage completed with unresolved profiles: "
                            f"failed={failed_count}, pending={pending_count}, running={running_count}."
                        ),
                    )
                else:
                    status_update.update({
                        "status": "completed",
                        "finished_at": datetime.now(timezone.utc),
                        "error_message": None,
                    })
                    await _append_run_log(db, run.id, "Posts stage completed.")
            await scrape_run_repo.update_run(db, run.id, status_update)
        except Exception as exc:
            await _append_run_log(db, run.id, f"Posts stage failed: {exc}")
            await scrape_run_repo.update_run(db, run.id, {
                "status": "failed",
                "embedding_status": "not_started" if fetched == 0 else embedding_status,
                "finished_at": datetime.now(timezone.utc),
                "items_fetched": fetched,
                "error_message": str(exc),
                "embedding_error_message": embedding_error_message,
            })

        await db.commit()
        await _purge_ignored_instagram_account(db)
    return fetched


async def run_profiles_scrape(
    usernames: list[str],
    trigger: str = "manual",
    schedule_id: int | None = None,
    frequency: str = "on_demand",
    shared_scraped_at: datetime | None = None,
    batch_mode: bool = False,
    enable_embeddings: bool = True,
    existing_run_id: int | None = None,
    finalize_run: bool = True,
    apify_token: str | None = None,
) -> int:
    resume_payload = build_profiles_resume_payload(
        usernames=usernames,
        trigger=trigger,
        schedule_id=schedule_id,
        frequency=frequency,
        batch_mode=batch_mode,
        enable_embeddings=enable_embeddings,
        apify_token=apify_token,
    )
    async with AsyncSessionLocal() as db:
        settings = get_settings()
        await _purge_ignored_instagram_account(db)
        requested_usernames = _clean_usernames(usernames)
        if existing_run_id is not None:
            run = await db.get(ScrapeRun, existing_run_id)
            if run is None:
                raise ValueError(f"Run {existing_run_id} not found")
            await scrape_run_repo.update_run(db, run.id, {
                "status": "running",
                "embedding_status": "pending" if enable_embeddings else "skipped",
                "profiles_requested": len(requested_usernames),
                "error_message": None,
                "embedding_error_message": None,
                "resume_payload": resume_payload,
            })
        else:
            run = await scrape_run_repo.create_run(db, {
                "scraper_type": "profiles",
                "trigger": trigger,
                "schedule_id": schedule_id,
                "embedding_status": "pending" if enable_embeddings else "skipped",
                "profiles_requested": len(requested_usernames),
                "resume_payload": resume_payload,
            })

        await scrape_run_repo.initialize_profile_progress(db, run.id, requested_usernames)
        target_usernames = await scrape_run_repo.get_usernames_for_resume(
            db,
            run.id,
            settings.scrape_resume_max_attempts,
        )
        await _append_run_log(db, run.id, f"Profiles stage started for {len(target_usernames)} pending profile(s).")
        await db.commit()

        logger.info("Starting profile checkpoint upsert flow for run %d", run.id)

        scraped_at = shared_scraped_at or datetime.now(timezone.utc)
        period_label = derive_period_label(frequency)
        fetched = int(run.items_fetched or 0)
        embedding_status = "pending" if enable_embeddings else "skipped"
        embedding_error_message: str | None = None
        missing_usernames: list[str] = []

        async def _fetch_profile_batch(username: str):
            return await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, partial(run_profiles_actor, [username], apify_token)
                ),
                timeout=max(60, int(get_settings().apify_actor_timeout_seconds)),
            )

        try:
            await _append_run_log(db, run.id, "Profiles stage: fetching profile batches from Apify...")
            await db.commit()

            for username in target_usernames:
                await scrape_run_repo.mark_profile_running(db, run.id, username)
                await _append_run_log(db, run.id, f"Profiles stage: scraping @{username}...")
                await db.commit()

                try:
                    result = await _fetch_profile_batch(username)
                    apify_metadata: dict[str, Any] = {}
                    if isinstance(result, tuple):
                        if len(result) >= 3:
                            raw_items, raw_logs, apify_metadata = result[0], result[1], result[2] or {}
                        else:
                            raw_items, raw_logs = result[0], result[1]
                    else:
                        raw_items, raw_logs = result, []

                    if apify_metadata:
                        await scrape_run_repo.update_apify_stage_metadata(
                            db,
                            run.id,
                            stage="profiles",
                            metadata=apify_metadata,
                            event_type="actor_call",
                            extra={
                                "username": _normalize_username_key(username),
                            },
                        )

                    if raw_logs:
                        await _extend_run_logs(db, run.id, raw_logs)

                    valid_profile_count = 0
                    for raw in raw_items:
                        norm = normalize_profile(raw)
                        if not norm["id"] or not norm["username"]:
                            continue

                        matched_by_history = False
                        if norm.get("id"):
                            hist_profile = await profile_repo.get_profile_by_handle_or_history(db, username)
                            if hist_profile and str(hist_profile.id) == str(norm["id"]):
                                matched_by_history = True

                        if _normalize_username_key(norm["username"]) != _normalize_username_key(username) and not matched_by_history:
                            continue

                        existing_profile = await db.get(Profile, norm["id"])
                        profile_image_urls = [norm.get("profile_pic_url_hd"), norm.get("profile_pic_url")]
                        should_upload_profile_pic = any(profile_image_urls)
                        if existing_profile and _is_supabase_storage_url(existing_profile.profile_pic_url):
                            norm["profile_pic_url"] = existing_profile.profile_pic_url
                            should_upload_profile_pic = False

                        if should_upload_profile_pic:
                            try:
                                upload_result = await asyncio.get_event_loop().run_in_executor(
                                    None,
                                    partial(upload_profile_image_to_supabase, profile_image_urls, norm["id"]),
                                )
                                if upload_result:
                                    norm["profile_pic_url"] = upload_result.public_url
                                else:
                                    logger.warning("Storage upload skipped for profile %s: no reachable image URL", norm["username"])
                            except Exception:
                                logger.warning("Storage upload failed for profile %s", norm["username"], exc_info=True)

                        profile = await profile_repo.upsert_profile(db, norm)
                        await _delete_profile_snapshot_for_run(db, run.id, profile.id)
                        await profile_repo.insert_snapshot(db, {
                            "profile_id": profile.id,
                            "followers_count": norm["followers_count"],
                            "follows_count": norm["follows_count"],
                            "posts_count": norm["posts_count"],
                            "period_label": period_label,
                            "run_id": run.id,
                            "scraped_at": scraped_at,
                        })
                        valid_profile_count += 1

                    if valid_profile_count == 0:
                        missing_usernames.append(username)
                        await scrape_run_repo.mark_profile_failed(
                            db,
                            run.id,
                            username,
                            "No profile data returned from Apify for this username.",
                        )
                        await _append_run_log(db, run.id, f"Profiles stage: no profile data for @{username}.")
                    else:
                        fetched += valid_profile_count
                        await scrape_run_repo.mark_profile_success(db, run.id, username, valid_profile_count)
                        await _append_run_log(db, run.id, f"Profiles stage: persisted @{username}.")

                    await scrape_run_repo.update_run(db, run.id, {"items_fetched": fetched})
                    await db.commit()
                except Exception as exc:
                    logger.warning("Profile scrape failed for %s", username, exc_info=exc)
                    await scrape_run_repo.mark_profile_failed(db, run.id, username, str(exc))
                    await _append_run_log(db, run.id, f"Profiles stage failed for @{username}: {exc}")
                    await scrape_run_repo.update_run(db, run.id, {"items_fetched": fetched})
                    await db.commit()

            await scrape_run_repo.update_run(db, run.id, {"missing_usernames": json.dumps(missing_usernames)})
            await db.commit()

            rows = await scrape_run_repo.get_profile_progress_rows(db, run.id)
            failed_count = len([row for row in rows if row.status == "failed"])

            if not enable_embeddings:
                embedding_status = "skipped"
            elif fetched == 0:
                embedding_status = "skipped"
            else:
                await db.refresh(run)
                if run.embedding_status == "skipped":
                    embedding_status = "skipped"
                else:
                    try:
                        await _append_run_log(db, run.id, "Profiles stage: generating embeddings...")
                        await db.commit()
                        await embed_and_index_profiles(db)
                        embedding_status = "completed"
                    except Exception as exc:
                        embedding_status = "failed"
                        embedding_error_message = str(exc)

            status_update = {
                "embedding_status": embedding_status,
                "items_fetched": fetched,
                "embedding_error_message": embedding_error_message,
            }
            if finalize_run:
                if failed_count:
                    status_update.update({
                        "status": "failed",
                        "finished_at": datetime.now(timezone.utc),
                        "error_message": f"Profiles stage completed with {failed_count} failed profile(s).",
                    })
                    await _append_run_log(db, run.id, f"Profiles stage completed with {failed_count} failed profile(s).")
                else:
                    status_update.update({
                        "status": "completed",
                        "finished_at": datetime.now(timezone.utc),
                        "error_message": None,
                    })
                    await _append_run_log(db, run.id, "Profiles stage completed.")
            else:
                await _append_run_log(db, run.id, "Profiles stage completed. Handing off to posts stage...")
            await scrape_run_repo.update_run(db, run.id, status_update)
        except Exception as exc:
            await _append_run_log(db, run.id, f"Profiles stage failed: {exc}")
            await scrape_run_repo.update_run(db, run.id, {
                "status": "failed",
                "embedding_status": "not_started" if fetched == 0 else embedding_status,
                "finished_at": datetime.now(timezone.utc),
                "items_fetched": fetched,
                "error_message": str(exc),
                "embedding_error_message": embedding_error_message,
            })
        await db.commit()
        await _purge_ignored_instagram_account(db)
    return fetched


async def run_combined_scrape(
    usernames: list[str],
    results_limit: int = 100,
    only_posts_newer_than: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    data_detail_level: str = "basicData",
    enable_embeddings: bool = True,
    batch_mode: bool = False,
    trigger: str = "manual",
    schedule_id: int | None = None,
    frequency: str = "on_demand",
    combined_run_id: int | None = None,
    apify_token: str | None = None,
) -> None:
    """
    Orchestrates a combined profile + post scrape in sequence using a shared timestamp.
    - First scrapes profiles
    - Then scrapes posts
    - Both use the same scraped_at timestamp for all records
    """
    # Generate a shared timestamp for both scrapers
    shared_scraped_at = datetime.now(timezone.utc)
    resume_payload = build_combined_resume_payload(
        usernames=usernames,
        trigger=trigger,
        schedule_id=schedule_id,
        frequency=frequency,
        results_limit=results_limit,
        only_posts_newer_than=only_posts_newer_than,
        date_from=date_from,
        date_to=date_to,
        data_detail_level=data_detail_level,
        batch_mode=batch_mode,
        enable_embeddings=enable_embeddings,
        apify_token=apify_token,
    )

    if combined_run_id is not None:
        async with AsyncSessionLocal() as db:
            await scrape_run_repo.update_run(db, combined_run_id, {"resume_payload": resume_payload})
            await _append_run_log(db, combined_run_id, "Combined scrape started.")
            await db.commit()

    # Run profiles scrape first
    await run_profiles_scrape(
        usernames,
        trigger=trigger,
        schedule_id=schedule_id,
        frequency=frequency,
        shared_scraped_at=shared_scraped_at,
        batch_mode=batch_mode,
        enable_embeddings=enable_embeddings,
        existing_run_id=combined_run_id,
        finalize_run=False,
        apify_token=apify_token,
    )

    if combined_run_id is not None:
        async with AsyncSessionLocal() as db:
            await scrape_run_repo.reset_profile_progress(db, combined_run_id)
            await scrape_run_repo.update_run(db, combined_run_id, {"items_fetched": 0})
            await _append_run_log(db, combined_run_id, "Starting posts stage...")
            await db.commit()

    # Then run posts scrape with the same timestamp
    await run_posts_scrape(
        usernames,
        scraper_type="posts",
        trigger=trigger,
        schedule_id=schedule_id,
        results_limit=results_limit,
        only_posts_newer_than=only_posts_newer_than,
        date_from=date_from,
        date_to=date_to,
        frequency=frequency,
        data_detail_level=data_detail_level,
        shared_scraped_at=shared_scraped_at,
        batch_mode=batch_mode,
        enable_embeddings=enable_embeddings,
        existing_run_id=combined_run_id,
        finalize_run=True,
        apify_token=apify_token,
    )


async def _resolve_run_usernames(db, run: ScrapeRun) -> list[str]:
    payload = _parse_resume_payload(run.resume_payload)
    payload_usernames = payload.get("usernames")
    if isinstance(payload_usernames, list) and payload_usernames:
        return _clean_usernames([str(value) for value in payload_usernames])

    progress_rows = await scrape_run_repo.get_profile_progress_rows(db, run.id)
    if progress_rows:
        return _clean_usernames([row.username for row in progress_rows])

    scrape_profiles_result = await db.execute(select(ScrapeProfile).order_by(ScrapeProfile.position, ScrapeProfile.id))
    return _clean_usernames([row.username for row in scrape_profiles_result.scalars().all()])


async def replay_posts_stage_from_apify_items(
    run_id: int,
    raw_items: list[dict[str, Any]],
    frequency: str = "on_demand",
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        run = await db.get(ScrapeRun, run_id)
        if run is None:
            raise ValueError(f"Run {run_id} not found")

        requested_usernames = await _resolve_run_usernames(db, run)
        requested_set = set(requested_usernames)

        await scrape_run_repo.update_run(db, run.id, {
            "status": "running",
            "finished_at": None,
            "error_message": None,
        })
        await _append_run_log(db, run.id, "Apify refetch: replaying posts stage into DB...")

        await db.execute(delete(PostSnapshotTaggedUser).where(PostSnapshotTaggedUser.run_id == run.id))
        await db.execute(delete(PostSnapshotMention).where(PostSnapshotMention.run_id == run.id))
        await db.execute(delete(PostSnapshotHashtag).where(PostSnapshotHashtag.run_id == run.id))
        await db.execute(delete(PostSnapshot).where(PostSnapshot.run_id == run.id))
        await scrape_run_repo.reset_profile_progress(db, run.id)
        await scrape_run_repo.initialize_profile_progress(db, run.id, requested_usernames)
        await db.commit()

        period_label = derive_period_label(frequency)
        scraped_at = datetime.now(timezone.utc)
        per_user_counts: dict[str, int] = {username: 0 for username in requested_usernames}
        imported = 0
        seen_post_keys: set[tuple[str, str]] = set()

        for raw in raw_items:
            norm = normalize_post(raw)
            url = norm.get("url", "")
            if not url:
                continue
            if not _is_timestamp_within_range(norm.get("timestamp"), date_from, date_to):
                continue

            owner_username = _normalize_username_key(norm.get("owner_username") or "")
            if not owner_username:
                continue
            if requested_set and owner_username not in requested_set:
                continue

            dedupe_key = (owner_username, url)
            if dedupe_key in seen_post_keys:
                continue
            seen_post_keys.add(dedupe_key)

            norm["owner_username"] = owner_username
            norm["id"] = _post_id(url, period_label)

            snap = await post_repo.insert_snapshot(db, {
                "post_id": norm["id"],
                "run_id": run.id,
                "owner_username": owner_username,
                "url": norm["url"],
                "timestamp": norm.get("timestamp"),
                "likes_count": norm.get("likes_count", 0) or 0,
                "video_play_count": norm.get("video_play_count", 0) or 0,
                "type": norm.get("type"),
                "video_url": norm.get("video_url"),
                "display_url": norm.get("display_url"),
                "display_storage_path": norm.get("display_storage_path"),
                "display_storage_url": norm.get("display_storage_url"),
                "caption": norm.get("caption"),
                "product_type": norm.get("product_type"),
                "input_url": norm.get("input_url"),
                "hashtags": norm.get("hashtags") or [],
                "mentions": norm.get("mentions") or [],
                "tagged_users": norm.get("tagged_users") or [],
                "coauthor_producers": norm.get("coauthor_producers") or [],
                "period_label": period_label,
                "scraped_at": scraped_at,
            })
            await post_repo.replace_snapshot_hashtags(
                db,
                snapshot_id=snap.id,
                post_id=norm["id"],
                run_id=run.id,
                period_label=period_label,
                owner_username=owner_username,
                hashtags=norm.get("hashtags") or [],
            )
            await post_repo.replace_snapshot_mentions(
                db,
                snapshot_id=snap.id,
                post_id=norm["id"],
                run_id=run.id,
                period_label=period_label,
                owner_username=owner_username,
                mentions=norm.get("mentions") or [],
            )
            await post_repo.replace_snapshot_tagged_users(
                db,
                snapshot_id=snap.id,
                post_id=norm["id"],
                run_id=run.id,
                period_label=period_label,
                owner_username=owner_username,
                tagged_users=norm.get("tagged_users") or [],
            )
            per_user_counts[owner_username] = per_user_counts.get(owner_username, 0) + 1
            imported += 1

        for username in requested_usernames:
            await scrape_run_repo.mark_profile_success(db, run.id, username, per_user_counts.get(username, 0))

        await scrape_run_repo.update_run(db, run.id, {
            "status": "completed",
            "finished_at": datetime.now(timezone.utc),
            "items_fetched": imported,
            "error_message": None,
        })
        await _append_run_log(db, run.id, f"Apify refetch replay complete for posts stage: imported {imported} post(s).")
        await db.commit()

        return {
            "run_id": run.id,
            "items_fetched": imported,
            "profiles_processed": len(requested_usernames),
        }


async def replay_profiles_stage_from_apify_items(
    run_id: int,
    raw_items: list[dict[str, Any]],
    frequency: str = "on_demand",
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        run = await db.get(ScrapeRun, run_id)
        if run is None:
            raise ValueError(f"Run {run_id} not found")

        requested_usernames = await _resolve_run_usernames(db, run)
        requested_set = set(requested_usernames)

        await scrape_run_repo.update_run(db, run.id, {
            "status": "running",
            "finished_at": None,
            "error_message": None,
        })
        await _append_run_log(db, run.id, "Apify refetch: replaying profiles stage into DB...")

        await db.execute(delete(ProfileSnapshot).where(ProfileSnapshot.run_id == run.id))
        await scrape_run_repo.reset_profile_progress(db, run.id)
        await scrape_run_repo.initialize_profile_progress(db, run.id, requested_usernames)
        await db.commit()

        period_label = derive_period_label(frequency)
        scraped_at = datetime.now(timezone.utc)
        imported = 0
        seen_usernames: set[str] = set()
        replayed_usernames: set[str] = set()

        for raw in raw_items:
            norm = normalize_profile(raw)
            profile_id = norm.get("id")
            username = _normalize_username_key(norm.get("username") or "")
            if not profile_id or not username:
                continue
            if requested_set and username not in requested_set:
                continue
            if username in replayed_usernames:
                continue
            replayed_usernames.add(username)

            profile = await profile_repo.upsert_profile(db, norm)
            await profile_repo.insert_snapshot(db, {
                "profile_id": profile.id,
                "followers_count": norm["followers_count"],
                "follows_count": norm["follows_count"],
                "posts_count": norm["posts_count"],
                "period_label": period_label,
                "run_id": run.id,
                "scraped_at": scraped_at,
            })
            seen_usernames.add(username)

        missing_usernames: list[str] = []
        for username in requested_usernames:
            if username in seen_usernames:
                await scrape_run_repo.mark_profile_success(db, run.id, username, 1)
                imported += 1
            else:
                missing_usernames.append(username)
                await scrape_run_repo.mark_profile_failed(
                    db,
                    run.id,
                    username,
                    "No profile data returned from Apify for this username.",
                )

        run_status = "failed" if missing_usernames else "completed"
        error_message = None if not missing_usernames else f"Profiles stage completed with {len(missing_usernames)} failed profile(s)."

        await scrape_run_repo.update_run(db, run.id, {
            "status": run_status,
            "finished_at": datetime.now(timezone.utc),
            "items_fetched": imported,
            "missing_usernames": json.dumps(missing_usernames),
            "error_message": error_message,
        })
        await _append_run_log(db, run.id, f"Apify refetch replay complete for profiles stage: imported {imported} profile(s).")
        await db.commit()

        return {
            "run_id": run.id,
            "items_fetched": imported,
            "profiles_processed": len(requested_usernames),
            "missing_usernames": missing_usernames,
        }


def _looks_like_post_url(url: str) -> bool:
    value = (url or "").lower()
    return "/p/" in value or "/reel/" in value or "/tv/" in value


def _parse_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


async def recover_posts_from_debug(run_id: int) -> dict:
    debug_path = Path(_DEBUG_DIR) / f"posts_run_{run_id}.json"
    if not debug_path.exists():
        raise FileNotFoundError(f"Debug file not found: {debug_path}")

    payload = json.loads(debug_path.read_text(encoding="utf-8"))
    normalized = payload.get("normalized") or []
    imported = 0
    skipped_non_post_url = 0

    async with AsyncSessionLocal() as db:
        run = await db.get(ScrapeRun, run_id)
        if run is None:
            raise ValueError(f"Run {run_id} not found")

        period_label = (run.started_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
        scraped_at = run.started_at or datetime.now(timezone.utc)
        snapshot_columns = set(PostSnapshot.__table__.columns.keys())

        for item in normalized:
            url = item.get("url")
            if not url or not _looks_like_post_url(url):
                skipped_non_post_url += 1
                continue

            row = dict(item)
            row["id"] = _post_id(url, period_label)
            row["period_label"] = period_label
            row["run_id"] = run_id
            row["scraped_at"] = scraped_at
            row["timestamp"] = _parse_dt(row.get("timestamp"))

            snap_data = {
                "post_id": row["id"],
                "run_id": run_id,
                "owner_username": row.get("owner_username"),
                "url": row["url"],
                "timestamp": row.get("timestamp"),
                "likes_count": row.get("likes_count", 0) or 0,
                "video_play_count": row.get("video_play_count", 0) or 0,
                "type": row.get("type"),
                "video_url": row.get("video_url"),
                "display_url": row.get("display_url"),
                "display_storage_path": row.get("display_storage_path"),
                "display_storage_url": row.get("display_storage_url"),
                "caption": row.get("caption"),
                "product_type": row.get("product_type"),
                "input_url": row.get("input_url"),
                "hashtags": row.get("hashtags") or [],
                "mentions": row.get("mentions") or [],
                "tagged_users": row.get("tagged_users") or [],
                "coauthor_producers": row.get("coauthor_producers") or [],
                "period_label": period_label,
                "scraped_at": scraped_at,
            }
            snap_data = {k: v for k, v in snap_data.items() if k in snapshot_columns}
            snap = await post_repo.insert_snapshot(db, snap_data)
            await post_repo.replace_snapshot_hashtags(
                db,
                snapshot_id=snap.id,
                post_id=row["id"],
                run_id=run_id,
                period_label=period_label,
                owner_username=row.get("owner_username"),
                hashtags=row.get("hashtags") or [],
            )
            await post_repo.replace_snapshot_mentions(
                db,
                snapshot_id=snap.id,
                post_id=row["id"],
                run_id=run_id,
                period_label=period_label,
                owner_username=row.get("owner_username"),
                mentions=row.get("mentions") or [],
            )
            await post_repo.replace_snapshot_tagged_users(
                db,
                snapshot_id=snap.id,
                post_id=row["id"],
                run_id=run_id,
                period_label=period_label,
                owner_username=row.get("owner_username"),
                tagged_users=row.get("tagged_users") or [],
            )
            imported += 1

        await scrape_run_repo.update_run(db, run_id, {
            "status": "completed",
            "embedding_status": "skipped",
            "items_fetched": imported,
            "error_message": None,
            "embedding_error_message": None,
            "finished_at": datetime.now(timezone.utc),
        })
        await db.commit()

        posts_rows = await db.scalar(select(func.count()).select_from(PostSnapshot).where(PostSnapshot.run_id == run_id))

    return {
        "run_id": run_id,
        "imported_posts": imported,
        "skipped_non_post_urls": skipped_non_post_url,
        "post_snapshot_rows": int(posts_rows or 0),
    }
