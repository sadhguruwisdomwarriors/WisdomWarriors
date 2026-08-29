import asyncio
import json
from functools import partial
from typing import Any
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.engine import get_db
from backend.config import get_settings
from backend.models.post_snapshot import PostSnapshot
from backend.models.profile_snapshot import ProfileSnapshot
from backend.models.scrape_run import ScrapeRun
from backend.schemas.scrape import (
    InsightRead,
    RunComparisonRead,
    ProfilesSourceRead,
    ProfilesSourceUpdate,
    ScrapeProfileRead,
    ScrapeProfileCreate,
    ScrapeProfileBulkCreate,
    ScrapeProfileBulkResult,
    ScrapeProfileUpdate,
    ScrapeDbUpdateStatus,
    ScrapeProfileAttemptRead,
    ScrapeProfileFailureRead,
    ScrapeProfileProgressListResponse,
    ScrapeProfileProgressRead,
    ScrapeProfileProgressRowRead,
    ScrapeRequest,
    CombinedScrapeRequest,
    ApifyRefetchRequest,
    ApifyRefetchRead,
    ScrapeStartRead,
    ScrapeStatusRead,
    ScrapeRunRead,
    ScrapeRunListResponse,
    ValidateHandlesRequest,
    ValidateHandlesResponseRead,
)
from backend.services.handle_validation_service import validate_and_resolve_handles
from backend.repositories.scrape_profile_repo import (
    list_scrape_profiles,
    replace_scrape_profiles,
    add_scrape_profile,
    add_scrape_profiles_bulk,
    update_scrape_profile_fields,
    delete_scrape_profile,
)
from backend.services.scrape_service import (
    run_posts_scrape,
    run_profiles_scrape,
    run_combined_scrape,
    recover_posts_from_debug,
    build_posts_resume_payload,
    build_profiles_resume_payload,
    build_combined_resume_payload,
    replay_posts_stage_from_apify_items,
    replay_profiles_stage_from_apify_items,
)
from backend.services.apify.run_refetch import refetch_apify_run_output
from backend.repositories.scrape_run_repo import (
    update_apify_stage_metadata,
    create_run,
    get_latest_post_deltas,
    get_profile_deltas,
    get_run_compare_summary,
    get_runs_by_ids,
    get_profile_progress_rows,
    list_profile_progress_rows,
    list_runs,
)

router = APIRouter(prefix="/api/scrape", tags=["scrape"])
RESUME_LOG_MARKER = "Server restarted; resuming scrape run from persisted settings."

_TERMINAL_FAILURE_HINTS = (
    "no profile data returned",
    "not found",
    "private",
    "invalid",
    "username does not exist",
)


def _classify_failure(error_message: str | None) -> str:
    message = (error_message or "").strip().lower()
    if not message:
        return "unknown"
    if any(hint in message for hint in _TERMINAL_FAILURE_HINTS):
        return "data"
    if "timeout" in message or "timed out" in message or "rate limit" in message or "429" in message:
        return "transient"
    if "connection" in message or "network" in message:
        return "transient"
    return "system"


def _is_retryable_failure(error_message: str | None) -> bool:
    category = _classify_failure(error_message)
    return category in ("transient", "system", "unknown")


def _resume_detected_from_raw_logs(raw_logs: str | None) -> bool:
    if not raw_logs:
        return False
    try:
        lines = json.loads(raw_logs)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(lines, list):
        return False
    return any(isinstance(line, str) and RESUME_LOG_MARKER in line for line in lines)


def _extract_apify_token_from_resume_payload(raw_payload: str | None) -> str | None:
    if not raw_payload:
        return None
    try:
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    token = payload.get("apify_token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


def _parse_resume_payload(raw_payload: str | None) -> dict:
    if not raw_payload:
        return {}
    try:
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _append_lines_to_raw_logs(raw_logs: str | None, lines_to_add: list[str], max_lines: int = 1200) -> str:
    lines: list[str] = []
    if raw_logs:
        try:
            loaded = json.loads(raw_logs)
            if isinstance(loaded, list):
                lines = [item for item in loaded if isinstance(item, str)]
        except (json.JSONDecodeError, TypeError):
            lines = []
    lines.extend([line for line in lines_to_add if isinstance(line, str)])
    return json.dumps(lines[-max_lines:])


def _load_apify_stage_history(raw_history: str | None) -> list[dict[str, Any]]:
    if not raw_history:
        return []
    try:
        loaded = json.loads(raw_history)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(loaded, list):
        return []
    return [row for row in loaded if isinstance(row, dict)]


def _collect_unique_apify_runs_for_stage(run: ScrapeRun, stage: str) -> list[tuple[str, str, str | None]]:
    stage_key = stage.strip().lower()
    history = _load_apify_stage_history(run.apify_stage_history)

    pairs: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    for event in history:
        if str(event.get("stage") or "").strip().lower() != stage_key:
            continue
        run_id = str(event.get("run_id") or "").strip()
        dataset_id = str(event.get("dataset_id") or "").strip()
        actor_id = str(event.get("actor_id") or "").strip() or None
        if not run_id or not dataset_id:
            continue
        key = (run_id, dataset_id)
        if key in seen:
            continue
        seen.add(key)
        pairs.append((run_id, dataset_id, actor_id))

    latest_run_id = str(getattr(run, f"apify_{stage_key}_run_id", "") or "").strip()
    latest_dataset_id = str(getattr(run, f"apify_{stage_key}_dataset_id", "") or "").strip()
    latest_actor_id = str(getattr(run, f"apify_{stage_key}_actor_id", "") or "").strip() or None
    if latest_run_id and latest_dataset_id and (latest_run_id, latest_dataset_id) not in seen:
        pairs.append((latest_run_id, latest_dataset_id, latest_actor_id))

    return pairs


def _build_insights(summary: dict, profile_deltas: list[dict], latest_post_deltas: list[dict]) -> list[InsightRead]:
    insights: list[InsightRead] = []

    net_followers_delta = int(summary.get("net_followers_delta", 0) or 0)
    follower_tone = "positive" if net_followers_delta > 0 else "negative" if net_followers_delta < 0 else "neutral"
    insights.append(
        InsightRead(
            title="Net Followers Delta",
            value=f"{net_followers_delta:+,}",
            detail="Follower change across compared profile snapshot rows.",
            tone=follower_tone,
        )
    )

    top_profile = next((row for row in profile_deltas if row.get("change_type") == "common"), None)
    if top_profile:
        insights.append(
            InsightRead(
                title="Top Profile Move",
                value=f"{top_profile['profile_id']} ({int(top_profile.get('followers_delta', 0)):+,})",
                detail="Largest absolute follower shift among profiles present in both runs.",
                tone="positive" if int(top_profile.get("followers_delta", 0)) >= 0 else "negative",
            )
        )

    net_likes_delta = int(summary.get("net_likes_delta", 0) or 0)
    likes_tone = "positive" if net_likes_delta > 0 else "negative" if net_likes_delta < 0 else "neutral"
    insights.append(
        InsightRead(
            title="Net Likes Delta",
            value=f"{net_likes_delta:+,}",
            detail="Like change across latest-post snapshots.",
            tone=likes_tone,
        )
    )

    top_post = next((row for row in latest_post_deltas if row.get("change_type") == "common"), None)
    if top_post:
        owner = top_post.get("owner_username") or top_post.get("profile_id")
        insights.append(
            InsightRead(
                title="Top Post Move",
                value=f"{owner} ({int(top_post.get('likes_delta', 0)):+,} likes)",
                detail="Largest like change among posts visible in both runs.",
                tone="positive" if int(top_post.get("likes_delta", 0)) >= 0 else "negative",
            )
        )

    new_profiles = int(summary.get("new_profiles", 0) or 0)
    missing_profiles = int(summary.get("missing_profiles", 0) or 0)
    insights.append(
        InsightRead(
            title="Coverage Shift",
            value=f"+{new_profiles} / -{missing_profiles}",
            detail="Profiles that appeared in run B vs missing from run B.",
            tone="neutral",
        )
    )

    return insights


@router.get("/profiles-source", response_model=ProfilesSourceRead)
async def get_profiles_source(db: AsyncSession = Depends(get_db)) -> ProfilesSourceRead:
    rows = await list_scrape_profiles(db)
    return ProfilesSourceRead(usernames=[row.username for row in rows])


@router.put("/profiles-source", response_model=ProfilesSourceRead)
async def update_profiles_source(body: ProfilesSourceUpdate, db: AsyncSession = Depends(get_db)) -> ProfilesSourceRead:
    usernames = await replace_scrape_profiles(db, body.usernames)
    await db.commit()
    return ProfilesSourceRead(usernames=usernames)


@router.post("/validate-handles", response_model=ValidateHandlesResponseRead)
async def validate_handles(
    body: ValidateHandlesRequest,
    db: AsyncSession = Depends(get_db),
) -> ValidateHandlesResponseRead:
    result = await validate_and_resolve_handles(db, body.handles, body.apify_token)
    return ValidateHandlesResponseRead.model_validate(result)


@router.post("/run", response_model=ScrapeStartRead)
async def trigger_scrape(
    req: ScrapeRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    usernames = req.usernames or [row.username for row in await list_scrape_profiles(db)]
    if req.scraper_type == "profiles":
        resume_payload = build_profiles_resume_payload(
            usernames=usernames,
            trigger="manual",
            schedule_id=None,
            frequency="on_demand",
            batch_mode=req.batch_mode,
            enable_embeddings=req.enable_embeddings,
            apify_token=req.apify_token,
        )
    else:
        resume_payload = build_posts_resume_payload(
            usernames=usernames,
            trigger="manual",
            schedule_id=None,
            results_limit=req.results_limit,
            only_posts_newer_than=req.only_posts_newer_than,
            date_from=req.date_from,
            date_to=req.date_to,
            frequency="on_demand",
            data_detail_level=req.data_detail_level,
            batch_mode=req.batch_mode,
            enable_embeddings=req.enable_embeddings,
            apify_token=req.apify_token,
        )

    run = await create_run(db, {
        "scraper_type": req.scraper_type,
        "trigger": "manual",
        "schedule_id": None,
        "embedding_status": "pending" if req.enable_embeddings else "skipped",
        "profiles_requested": len(usernames),
        "resume_payload": resume_payload,
        "raw_logs": json.dumps([
            f"{req.scraper_type.title()} scrape queued for {len(usernames)} profile(s).",
        ]),
    })
    await db.commit()

    if req.scraper_type == "profiles":
        background.add_task(
            run_profiles_scrape,
            usernames=usernames,
            trigger="manual",
            schedule_id=None,
            frequency="on_demand",
            shared_scraped_at=None,
            batch_mode=req.batch_mode,
            enable_embeddings=req.enable_embeddings,
            existing_run_id=run.id,
            finalize_run=True,
            apify_token=req.apify_token,
        )
    else:
        background.add_task(
            run_posts_scrape,
            usernames=usernames,
            scraper_type="posts",
            trigger="manual",
            schedule_id=None,
            results_limit=req.results_limit,
            only_posts_newer_than=req.only_posts_newer_than,
            date_from=req.date_from,
            date_to=req.date_to,
            frequency="on_demand",
            data_detail_level=req.data_detail_level,
            shared_scraped_at=None,
            batch_mode=req.batch_mode,
            enable_embeddings=req.enable_embeddings,
            existing_run_id=run.id,
            finalize_run=True,
            apify_token=req.apify_token,
        )
    return {"status": "started", "profiles_count": len(usernames), "action": req.scraper_type, "run_id": run.id}


@router.post("/run/combined", response_model=ScrapeStartRead)
async def trigger_combined_scrape(
    req: CombinedScrapeRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Trigger a combined profile + post scrape.
    Profiles are scraped first, then posts, using the same scraped_at timestamp for all records.
    """
    usernames = req.usernames or [row.username for row in await list_scrape_profiles(db)]
    resume_payload = build_combined_resume_payload(
        usernames=usernames,
        trigger="manual",
        schedule_id=None,
        frequency="on_demand",
        results_limit=req.results_limit,
        only_posts_newer_than=req.only_posts_newer_than,
        date_from=req.date_from,
        date_to=req.date_to,
        data_detail_level=req.data_detail_level,
        batch_mode=req.batch_mode,
        enable_embeddings=req.enable_embeddings,
        apify_token=req.apify_token,
    )
    run = await create_run(db, {
        "scraper_type": "combined",
        "trigger": "manual",
        "schedule_id": None,
        "embedding_status": "pending" if req.enable_embeddings else "skipped",
        "profiles_requested": len(usernames),
        "resume_payload": resume_payload,
        "raw_logs": json.dumps([
            f"Combined scrape queued for {len(usernames)} profile(s).",
            "Preparing profiles stage...",
        ]),
    })
    await db.commit()
    background.add_task(
        run_combined_scrape,
        usernames=usernames,
        results_limit=req.results_limit,
        only_posts_newer_than=req.only_posts_newer_than,
        date_from=req.date_from,
        date_to=req.date_to,
        data_detail_level=req.data_detail_level,
        enable_embeddings=req.enable_embeddings,
        batch_mode=req.batch_mode,
        trigger="manual",
        schedule_id=None,
        frequency="on_demand",
        combined_run_id=run.id,
        apify_token=req.apify_token,
    )
    return {"status": "started", "profiles_count": len(usernames), "action": "combined_scrape", "run_id": run.id}


@router.get("/runs", response_model=ScrapeRunListResponse)
async def get_runs(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> ScrapeRunListResponse:
    items, total = await list_runs(db, status, limit, offset)
    parsed_items: list[ScrapeRunRead] = []
    for run in items:
        run_read = ScrapeRunRead.model_validate(run)
        parsed_items.append(
            run_read.model_copy(update={
                "resume_detected": _resume_detected_from_raw_logs(run.raw_logs),
            })
        )
    return ScrapeRunListResponse(items=parsed_items, total=total)


@router.post("/runs/{run_id}/apify-refetch", response_model=ApifyRefetchRead)
async def refetch_run_from_apify(
    run_id: int,
    req: ApifyRefetchRequest,
    db: AsyncSession = Depends(get_db),
) -> ApifyRefetchRead:
    run = await db.get(ScrapeRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status == "running":
        raise HTTPException(status_code=409, detail="Run is currently running")

    stage = req.stage
    stage_runs = _collect_unique_apify_runs_for_stage(run, stage)
    if not stage_runs:
        raise HTTPException(status_code=400, detail=f"No stored Apify metadata for stage '{stage}'")

    apify_token = _extract_apify_token_from_resume_payload(run.resume_payload)
    payload = _parse_resume_payload(run.resume_payload)
    frequency = str(payload.get("frequency") or "on_demand")
    date_from = payload.get("date_from")
    date_to = payload.get("date_to")

    loop = asyncio.get_event_loop()
    all_items: list[dict[str, Any]] = []
    all_logs: list[str] = []
    latest_metadata: dict[str, Any] = {}

    for external_run_id, dataset_id, actor_id in stage_runs:
        items, logs, metadata = await loop.run_in_executor(
            None,
            partial(refetch_apify_run_output, external_run_id, dataset_id, apify_token),
        )
        metadata["actor_id"] = actor_id
        await update_apify_stage_metadata(
            db,
            run.id,
            stage=stage,
            metadata=metadata,
            event_type="refetch",
            extra={
                "items_count": len(items),
                "logs_count": len(logs),
            },
        )
        all_items.extend(items)
        all_logs.extend(logs)
        latest_metadata = metadata

    summary_line = (
        f"Apify refetch ({stage}) completed: unique_runs={len(stage_runs)}, "
        f"items={len(all_items)}, logs={len(all_logs)}"
    )
    if req.include_logs:
        run.raw_logs = _append_lines_to_raw_logs(run.raw_logs, [summary_line, *all_logs])
    else:
        run.raw_logs = _append_lines_to_raw_logs(run.raw_logs, [summary_line])
    await db.commit()

    if stage == "posts":
        replay_result = await replay_posts_stage_from_apify_items(
            run_id=run.id,
            raw_items=all_items,
            frequency=frequency,
            date_from=date_from if isinstance(date_from, str) else None,
            date_to=date_to if isinstance(date_to, str) else None,
        )
    else:
        replay_result = await replay_profiles_stage_from_apify_items(
            run_id=run.id,
            raw_items=all_items,
            frequency=frequency,
        )

    return ApifyRefetchRead(
        run_id=run.id,
        stage=stage,
        apify_run_id=str(latest_metadata.get("run_id") or stage_runs[-1][0]),
        apify_dataset_id=str(latest_metadata.get("dataset_id") or stage_runs[-1][1]),
        apify_status=str(latest_metadata.get("status") or "") or None,
        items_count=int(replay_result.get("items_fetched", len(all_items))),
        logs_count=len(all_logs),
        status="refetched",
    )


@router.get("/runs/{run_id}/profile-progress", response_model=ScrapeProfileProgressListResponse)
async def get_run_profile_progress(
    run_id: int,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> ScrapeProfileProgressListResponse:
    run = await db.get(ScrapeRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    rows, total = await list_profile_progress_rows(db, run_id, status, limit, offset)
    return ScrapeProfileProgressListResponse(
        items=[
            ScrapeProfileProgressRowRead(
                username=row.username,
                status=row.status,
                attempt_count=int(row.attempt_count or 0),
                items_fetched=int(row.items_fetched or 0),
                error_message=row.error_message,
                started_at=row.started_at,
                finished_at=row.finished_at,
                last_checkpoint_at=row.last_checkpoint_at,
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/status", response_model=ScrapeStatusRead)
async def get_scrape_status(
    run_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> ScrapeStatusRead:
    if run_id is not None:
        run = await db.get(ScrapeRun, run_id)
    else:
        running_result = await db.execute(
            select(ScrapeRun)
            .where(ScrapeRun.status == "running")
            .order_by(ScrapeRun.started_at.desc())
            .limit(1)
        )
        run = running_result.scalar_one_or_none()
        if run is None:
            latest_result = await db.execute(select(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(1))
            run = latest_result.scalar_one_or_none()

    if run is None:
        return ScrapeStatusRead(
            run=None,
            progress_pct=0,
            db_updates=ScrapeDbUpdateStatus(),
            profile_progress=ScrapeProfileProgressRead(),
            resume_detected=False,
            logs=["No scrape run found yet."],
        )

    progress_rows = await get_profile_progress_rows(db, run.id)
    completed_profiles = [row.username for row in progress_rows if row.status == "success"]
    pending_profiles = [row.username for row in progress_rows if row.status == "pending"]
    running_profiles = [row.username for row in progress_rows if row.status == "running"]
    failed_profiles_rows = [row for row in progress_rows if row.status == "failed"]
    settings = get_settings()
    retryable_failed_rows = [row for row in failed_profiles_rows if _is_retryable_failure(row.error_message)]
    terminal_failed_rows = [row for row in failed_profiles_rows if not _is_retryable_failure(row.error_message)]

    zero_posts_profiles = [row.username for row in progress_rows if row.status == "success" and int(row.items_fetched or 0) == 0]

    # Use immutable snapshot rows for per-run counts so values do not drop
    # when canonical Post rows are updated by later runs.
    posts_rows = await db.scalar(select(func.count()).select_from(PostSnapshot).where(PostSnapshot.run_id == run.id))
    snapshots_rows = await db.scalar(select(func.count()).select_from(ProfileSnapshot).where(ProfileSnapshot.run_id == run.id))
    profiles_touched = await db.scalar(
        select(func.count(func.distinct(ProfileSnapshot.profile_id))).where(ProfileSnapshot.run_id == run.id)
    )
    missing_usernames: list[str] = []
    aggregated_raw_logs: list[str] = []

    if run.missing_usernames:
        try:
            missing_usernames = json.loads(run.missing_usernames)
        except (json.JSONDecodeError, TypeError):
            missing_usernames = []
    if run.raw_logs:
        try:
            aggregated_raw_logs.extend(json.loads(run.raw_logs))
        except (json.JSONDecodeError, TypeError):
            pass

    # Combined profile->posts flow writes profile rows in a different run_id but shares
    # the same scraped_at timestamp. For posts runs, merge related profile counts by timestamp.
    if run.scraper_type == "posts":
        shared_scraped_at = await db.scalar(
            select(func.max(PostSnapshot.scraped_at)).where(PostSnapshot.run_id == run.id)
        )
        if shared_scraped_at is not None:
            snapshots_rows = await db.scalar(
                select(func.count())
                .select_from(ProfileSnapshot)
                .where(ProfileSnapshot.scraped_at == shared_scraped_at)
            )
            profiles_touched = await db.scalar(
                select(func.count(func.distinct(ProfileSnapshot.profile_id)))
                .where(ProfileSnapshot.scraped_at == shared_scraped_at)
            )
            profile_run_id = await db.scalar(
                select(ProfileSnapshot.run_id)
                .where(ProfileSnapshot.scraped_at == shared_scraped_at)
                .limit(1)
            )
            if profile_run_id is not None:
                profile_run = await db.get(ScrapeRun, profile_run_id)
                if profile_run and profile_run.missing_usernames:
                    try:
                        missing_usernames = json.loads(profile_run.missing_usernames)
                    except (json.JSONDecodeError, TypeError):
                        missing_usernames = []
                if profile_run and profile_run.raw_logs:
                    try:
                        aggregated_raw_logs = json.loads(profile_run.raw_logs) + aggregated_raw_logs
                    except (json.JSONDecodeError, TypeError):
                        pass

        # For a still-running posts scrape with no PostSnapshot rows yet (Apify call in progress),
        # show the most recently completed profiles run logs so the live log isn't blank.
        if run.status == "running" and posts_rows == 0 and not aggregated_raw_logs:
            prev_profile_run_result = await db.execute(
                select(ScrapeRun)
                .where(ScrapeRun.scraper_type == "profiles")
                .where(ScrapeRun.status == "completed")
                .where(ScrapeRun.started_at <= run.started_at)
                .order_by(ScrapeRun.finished_at.desc())
                .limit(1)
            )
            prev_profile_run = prev_profile_run_result.scalar_one_or_none()
            if prev_profile_run:
                if prev_profile_run.missing_usernames and not missing_usernames:
                    try:
                        missing_usernames = json.loads(prev_profile_run.missing_usernames)
                    except (json.JSONDecodeError, TypeError):
                        pass
                if prev_profile_run.raw_logs:
                    try:
                        aggregated_raw_logs = json.loads(prev_profile_run.raw_logs)
                    except (json.JSONDecodeError, TypeError):
                        pass

    processed_count = run.items_fetched
    if progress_rows:
        processed_profiles = len(completed_profiles) + len(failed_profiles_rows)
        if run.scraper_type in ("profiles", "combined", "posts"):
            processed_count = min(run.profiles_requested, processed_profiles)
    elif run.scraper_type == "profiles":
        # Legacy runs without checkpoints.
        processed_count = min(run.profiles_requested, run.items_fetched + len(missing_usernames))

    if run.scraper_type == "combined":
        if run.status == "completed":
            progress_pct = 100
        elif posts_rows > 0 or run.items_fetched > 0:
            progress_pct = min(99, 70 + min(run.items_fetched, 29))
        elif profiles_touched > 0:
            progress_pct = min(69, max(10, int((profiles_touched / max(run.profiles_requested, 1)) * 60)))
        else:
            progress_pct = 5
    elif run.status == "completed":
        progress_pct = 100
    elif run.profiles_requested > 0:
        progress_pct = min(99, int((processed_count / max(run.profiles_requested, 1)) * 100))
    else:
        progress_pct = 0

    logs = [
        f"Run #{run.id} started ({run.scraper_type}, {run.trigger}).",
        f"Progress: {processed_count}/{run.profiles_requested} processed.",
        f"DB updates: posts={posts_rows}, snapshots={snapshots_rows}.",
    ]
    if run.embedding_status:
        logs.append(f"Embedding status: {run.embedding_status}.")
    if run.status == "completed":
        logs.append("Run completed.")
    elif run.status == "failed":
        logs.append(f"Run failed: {run.error_message or 'unknown error'}")
    elif run.scraper_type == "combined":
        if posts_rows > 0:
            logs.append(f"Posts stage is in progress. Persisted {posts_rows} post snapshot row(s) so far.")
        elif profiles_touched > 0:
            logs.append(f"Profiles stage is in progress. Persisted {profiles_touched}/{run.profiles_requested} profile(s) so far.")
        else:
            logs.append("Combined scrape is initializing...")
    else:
        profile_fetch_finished = False
        if run.scraper_type == "profiles" and aggregated_raw_logs:
            profile_fetch_finished = any(
                isinstance(line, str)
                and (
                    "Status: SUCCEEDED" in line
                    or "[Status message]: Scraper finished" in line
                    or "CheerioCrawler: Finished!" in line
                )
                for line in aggregated_raw_logs
            )
        if run.scraper_type == "profiles" and processed_count >= run.profiles_requested:
            logs.append("Profile scrape finished. Finalizing embedding/indexing...")
        elif run.scraper_type == "profiles" and profile_fetch_finished:
            logs.append(
                f"Profile fetch is done at Apify. Backend is persisting results to DB ({processed_count}/{run.profiles_requested})..."
            )
        elif run.scraper_type == "posts" and run.items_fetched == 0:
            logs.append("Posts scraper: waiting for Apify actor to return results (this may take a few minutes)...")
        else:
            logs.append("Run still in progress...")
    if run.embedding_error_message:
        logs.append(f"Embedding error: {run.embedding_error_message}")
    if missing_usernames:
        logs.append(f"Missing profiles ({len(missing_usernames)}): {', '.join(missing_usernames)}")
    
    # Include raw scraper logs if available.
    if aggregated_raw_logs:
        logs.extend(aggregated_raw_logs)

    resume_detected = any(
        isinstance(line, str) and RESUME_LOG_MARKER in line
        for line in logs
    )

    return ScrapeStatusRead(
        run=run,
        progress_pct=progress_pct,
        db_updates=ScrapeDbUpdateStatus(
            posts_rows=posts_rows or 0,
            profile_snapshots_rows=snapshots_rows or 0,
            profiles_touched=profiles_touched or 0,
            missing_usernames=missing_usernames,
        ),
        profile_progress=ScrapeProfileProgressRead(
            total_profiles=run.profiles_requested,
            completed_count=len(completed_profiles),
            pending_count=len(pending_profiles),
            failed_count=len(failed_profiles_rows),
            retryable_failed_count=len(retryable_failed_rows),
            terminal_failed_count=len(terminal_failed_rows),
            running_count=len(running_profiles),
            completed_profiles=completed_profiles,
            pending_profiles=pending_profiles,
            failed_profiles=[
                ScrapeProfileFailureRead(
                    username=row.username,
                    attempt_count=int(row.attempt_count or 0),
                    error_message=row.error_message,
                    failure_category=_classify_failure(row.error_message),
                    retryable=_is_retryable_failure(row.error_message)
                    and int(row.attempt_count or 0) < int(settings.scrape_resume_max_attempts or 0),
                    retries_left=max(0, int(settings.scrape_resume_max_attempts or 0) - int(row.attempt_count or 0)),
                )
                for row in failed_profiles_rows
            ],
            zero_posts_profiles=zero_posts_profiles,
            profile_attempts=[
                ScrapeProfileAttemptRead(
                    username=row.username,
                    status=row.status,
                    attempt_count=int(row.attempt_count or 0),
                )
                for row in progress_rows
            ],
            server_failure_message=run.error_message if run.status == "failed" else None,
        ),
        resume_detected=resume_detected,
        logs=logs,
    )


@router.patch("/runs/{run_id}/skip-embedding", response_model=ScrapeRunRead)
async def skip_embedding(run_id: int, db: AsyncSession = Depends(get_db)) -> ScrapeRun:
    run = await db.get(ScrapeRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.embedding_status not in ("pending",):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot skip: embedding status is already '{run.embedding_status}'",
        )
    run.embedding_status = "skipped"
    await db.commit()
    await db.refresh(run)
    return run


@router.post("/runs/{run_id}/resume-pending-posts", response_model=ScrapeStartRead)
async def resume_pending_posts_for_run(
    run_id: int,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> ScrapeStartRead:
    run = await db.get(ScrapeRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.scraper_type not in ("posts", "combined"):
        raise HTTPException(status_code=409, detail="Pending-post resume is only supported for post runs")
    if run.status == "running":
        raise HTTPException(status_code=409, detail="Run is already in progress")

    progress_rows = await get_profile_progress_rows(db, run.id)
    pending_or_failed = [row for row in progress_rows if row.status in ("pending", "failed", "running")]
    if not pending_or_failed:
        raise HTTPException(status_code=409, detail="No pending or failed profiles found for this run")

    all_usernames = [row.username for row in progress_rows if row.username]
    if not all_usernames:
        all_usernames = [row.username for row in await list_scrape_profiles(db)]

    resume_payload = {}
    if run.resume_payload:
        try:
            parsed = json.loads(run.resume_payload)
            if isinstance(parsed, dict):
                resume_payload = parsed
        except (json.JSONDecodeError, TypeError):
            resume_payload = {}

    results_limit = int(resume_payload.get("results_limit") or 100)
    only_posts_newer_than = resume_payload.get("only_posts_newer_than")
    date_from = resume_payload.get("date_from")
    date_to = resume_payload.get("date_to")
    frequency = str(resume_payload.get("frequency") or "on_demand")
    data_detail_level = str(resume_payload.get("data_detail_level") or "basicData")
    batch_mode = bool(resume_payload.get("batch_mode", False))
    enable_embeddings = bool(resume_payload.get("enable_embeddings", True))
    apify_token = resume_payload.get("apify_token")

    background.add_task(
        run_posts_scrape,
        usernames=all_usernames,
        scraper_type="posts",
        trigger=str(run.trigger or "manual"),
        schedule_id=run.schedule_id,
        results_limit=results_limit,
        only_posts_newer_than=only_posts_newer_than,
        date_from=date_from,
        date_to=date_to,
        frequency=frequency,
        data_detail_level=data_detail_level,
        shared_scraped_at=None,
        batch_mode=batch_mode,
        enable_embeddings=enable_embeddings,
        existing_run_id=run.id,
        finalize_run=True,
        apify_token=apify_token,
    )

    return ScrapeStartRead(
        status="started",
        profiles_count=len(all_usernames),
        run_id=run.id,
        action="resume_pending_posts",
    )


@router.post("/runs/{run_id}/recover-debug")
async def recover_run_from_debug(run_id: int) -> dict:
    return await recover_posts_from_debug(run_id)


@router.get("/runs/compare", response_model=RunComparisonRead)
async def compare_runs(
    run_a_id: int,
    run_b_id: int,
    profile_limit: int = 50,
    latest_post_limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> RunComparisonRead:
    if run_a_id == run_b_id:
        raise HTTPException(status_code=400, detail="Please choose two different runs")

    runs = await get_runs_by_ids(db, [run_a_id, run_b_id])
    run_map = {run.id: run for run in runs}
    run_a = run_map.get(run_a_id)
    run_b = run_map.get(run_b_id)
    if run_a is None or run_b is None:
        raise HTTPException(status_code=404, detail="One or both runs were not found")
    if run_a.status != "completed" or run_b.status != "completed":
        raise HTTPException(status_code=409, detail="Run comparison is available only for completed runs")

    summary = await get_run_compare_summary(db, run_a_id, run_b_id)
    profile_deltas = await get_profile_deltas(db, run_a_id, run_b_id, limit=profile_limit)
    latest_post_deltas = await get_latest_post_deltas(db, run_a_id, run_b_id, limit=latest_post_limit)
    insights = _build_insights(summary, profile_deltas, latest_post_deltas)

    return RunComparisonRead(
        run_a=run_a,
        run_b=run_b,
        summary=summary,
        profile_deltas=profile_deltas,
        latest_post_deltas=latest_post_deltas,
        insights=insights,
    )


# ── Wisdom Warriors influencer management ─────────────────────────────────────

@router.get("/wisdom-warriors", response_model=list[ScrapeProfileRead])
async def list_wisdom_warriors(db: AsyncSession = Depends(get_db)) -> list[ScrapeProfileRead]:
    rows = await list_scrape_profiles(db)
    if not rows:
        return []
    usernames_lower = [r.username.lower() for r in rows]
    pic_result = await db.execute(
        text("SELECT lower(username), profile_pic_url FROM profiles WHERE lower(username) = ANY(:u)"),
        {"u": usernames_lower},
    )
    pic_map: dict[str, str | None] = {row[0]: row[1] for row in pic_result.fetchall()}
    return [
        ScrapeProfileRead(
            id=r.id,
            username=r.username,
            category=r.category,
            grade=r.grade,
            position=r.position,
            profile_pic_url=pic_map.get(r.username.lower()),
        )
        for r in rows
    ]


@router.post("/wisdom-warriors", response_model=ScrapeProfileRead, status_code=201)
async def create_wisdom_warrior(body: ScrapeProfileCreate, db: AsyncSession = Depends(get_db)) -> ScrapeProfileRead:
    profile = await add_scrape_profile(db, body.username, body.category, body.grade)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.post("/wisdom-warriors/bulk", response_model=ScrapeProfileBulkResult, status_code=201)
async def bulk_create_wisdom_warriors(
    body: ScrapeProfileBulkCreate,
    db: AsyncSession = Depends(get_db),
) -> ScrapeProfileBulkResult:
    if not body.profiles:
        raise HTTPException(status_code=400, detail="profiles is required")

    created, skipped_existing = await add_scrape_profiles_bulk(
        db,
        [item.model_dump() for item in body.profiles],
    )
    await db.commit()

    return ScrapeProfileBulkResult(
        created=[ScrapeProfileRead.model_validate(profile) for profile in created],
        skipped_existing=skipped_existing,
    )


@router.patch("/wisdom-warriors/{profile_id}", response_model=ScrapeProfileRead)
async def update_wisdom_warrior(
    profile_id: int,
    body: ScrapeProfileUpdate,
    db: AsyncSession = Depends(get_db),
) -> ScrapeProfileRead:
    profile = await update_scrape_profile_fields(
        db, profile_id,
        username=body.username if "username" in body.model_fields_set else None,
        category=body.category if "category" in body.model_fields_set else None,
        grade=body.grade if "grade" in body.model_fields_set else None,
        set_fields=body.model_fields_set,
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    await db.commit()
    await db.refresh(profile)
    return profile


@router.delete("/wisdom-warriors/{profile_id}", status_code=204)
async def delete_wisdom_warrior(profile_id: int, db: AsyncSession = Depends(get_db)) -> None:
    deleted = await delete_scrape_profile(db, profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found")
    await db.commit()


# ── Google Sheets Sync Endpoints ───────────────────────────────────────────────

from pydantic import BaseModel
from typing import Optional
from backend.services.google_sheets_sync_service import analyze_google_sheets, apply_google_sheets_sync

class GoogleSheetsSyncApplyRequest(BaseModel):
    channels_to_add: list[dict]
    handles_to_update: Optional[list[dict]] = None

@router.get("/wisdom-warriors/sync/preview")
@router.post("/wisdom-warriors/sync/preview")
async def preview_google_sheets_sync(db: AsyncSession = Depends(get_db)):
    try:
        return await analyze_google_sheets(db)
    except Exception as e:
        logger.error("Failed to analyze Google Sheets: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to analyze Google Sheets: {str(e)}")

@router.post("/wisdom-warriors/sync/apply")
async def apply_sync_from_google_sheets(
    body: GoogleSheetsSyncApplyRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        return await apply_google_sheets_sync(db, body.channels_to_add, body.handles_to_update)
    except Exception as e:
        logger.error("Failed to apply Google Sheets sync: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to apply sync: {str(e)}")
