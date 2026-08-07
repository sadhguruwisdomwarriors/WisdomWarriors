from datetime import datetime
from typing import Any, TypedDict
from backend.services.apify.client import get_apify_client
from backend.config import get_settings


class ApifyRunMetadata(TypedDict, total=False):
    actor_id: str
    run_id: str
    dataset_id: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _prepare_usernames(usernames: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in usernames:
        username = (item or "").strip().lstrip("@")
        if not username:
            continue
        key = username.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(username)
    return cleaned


def run_posts_actor(
    usernames: list[str],
    results_limit: int = 100,
    only_posts_newer_than: str | None = None,
    data_detail_level: str = "basicData",
    apify_token: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], ApifyRunMetadata]:
    settings = get_settings()
    client = get_apify_client(apify_token)
    prepared_usernames = _prepare_usernames(usernames)
    effective_results_limit = max(results_limit, len(prepared_usernames))
    run_input: dict[str, Any] = {
        "username": prepared_usernames,
        "resultsLimit": effective_results_limit,
        "skipPinnedPosts": True,
        "dataDetailLevel": data_detail_level,
    }
    if only_posts_newer_than:
        value = only_posts_newer_than.strip()
        run_input["onlyPostsNewerThan"] = value if "day" in value.lower() else f"{value} days"

    run_obj = client.actor(settings.apify_posts_actor_id).call(run_input=run_input)
        # --- BUG FIX: Safely convert 'Run' object to dictionary if needed ---
    if not isinstance(run_obj, dict):
        try:
            run = run_obj.model_dump() if hasattr(run_obj, "model_dump") else run_obj.dict() if hasattr(run_obj, "dict") else vars(run_obj)
        except Exception:
            run = {k: getattr(run_obj, k) for k in dir(run_obj) if not k.startswith('_')}
            
        # Add aliases so the old camelCase code still works perfectly!
        if "default_dataset_id" in run: run["defaultDatasetId"] = run["default_dataset_id"]
        if "started_at" in run: run["startedAt"] = run["started_at"]
        if "finished_at" in run: run["finishedAt"] = run["finished_at"]
    else:
        run = run_obj
    # --------------------------------------------------------------------
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    
    # Capture logs from the run
    logs = []
    try:
        log_content = client.run(run["id"]).log().get()
        # Split log content into lines for better display
        logs = [line.strip() for line in log_content.split('\n') if line.strip()]
    except Exception:
        pass  # If log retrieval fails, just skip it
    
    metadata: ApifyRunMetadata = {
        "actor_id": settings.apify_posts_actor_id,
        "run_id": str(run.get("id", "")),
        "dataset_id": str(run.get("defaultDatasetId", "")),
        "status": str(run.get("status", "")),
        "started_at": _parse_datetime(run.get("startedAt")),
        "finished_at": _parse_datetime(run.get("finishedAt")),
    }

    return items, logs, metadata
