from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel


class ScrapeRunRead(BaseModel):
    id: int
    scraper_type: str
    trigger: str
    schedule_id: Optional[int] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    embedding_status: str
    profiles_requested: int
    items_fetched: int
    error_message: Optional[str] = None
    embedding_error_message: Optional[str] = None
    resume_detected: bool = False
    apify_posts_actor_id: Optional[str] = None
    apify_posts_run_id: Optional[str] = None
    apify_posts_dataset_id: Optional[str] = None
    apify_posts_started_at: Optional[datetime] = None
    apify_posts_finished_at: Optional[datetime] = None
    apify_posts_status: Optional[str] = None
    apify_profiles_actor_id: Optional[str] = None
    apify_profiles_run_id: Optional[str] = None
    apify_profiles_dataset_id: Optional[str] = None
    apify_profiles_started_at: Optional[datetime] = None
    apify_profiles_finished_at: Optional[datetime] = None
    apify_profiles_status: Optional[str] = None
    apify_stage_history: Optional[str] = None

    model_config = {"from_attributes": True}


class ValidateHandlesRequest(BaseModel):
    handles: list[str]
    apify_token: Optional[str] = None


class HandleValidationItemRead(BaseModel):
    submitted_handle: str
    normalized_handle: str
    status: str              # 'FOUND' | 'NOT_FOUND' | 'ERROR'
    instagram_id: Optional[str] = None
    current_handle: Optional[str] = None
    source: Optional[str] = None       # 'database' | 'apify_lookup'
    instagram_url: str
    error_message: Optional[str] = None


class ValidateHandlesResponseRead(BaseModel):
    total: int
    found_count: int
    not_found_count: int
    error_count: int
    results: list[HandleValidationItemRead]


class ScrapeRequest(BaseModel):
    scraper_type: str                       # 'posts' | 'profiles'
    usernames: Optional[list[str]] = None   # override profiles file
    batch_mode: bool = False
    results_limit: int = 100
    only_posts_newer_than: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    data_detail_level: Literal["basicData", "detailedData"] = "basicData"
    enable_embeddings: bool = True
    apify_token: Optional[str] = None


class CombinedScrapeRequest(BaseModel):
    """Request for combined profile + post scrape"""
    usernames: Optional[list[str]] = None   # override profiles file
    batch_mode: bool = False
    results_limit: int = 100
    only_posts_newer_than: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    data_detail_level: Literal["basicData", "detailedData"] = "basicData"
    enable_embeddings: bool = True
    apify_token: Optional[str] = None


class ScrapeStartRead(BaseModel):
    status: str
    profiles_count: int
    run_id: int
    action: Optional[str] = None


class ApifyRefetchRequest(BaseModel):
    stage: Literal["posts", "profiles"]
    include_logs: bool = True


class ApifyRefetchRead(BaseModel):
    run_id: int
    stage: Literal["posts", "profiles"]
    apify_run_id: str
    apify_dataset_id: str
    apify_status: Optional[str] = None
    items_count: int = 0
    logs_count: int = 0
    status: str = "refetched"


class ScrapeRunListResponse(BaseModel):
    items: list[ScrapeRunRead]
    total: int


class ProfilesSourceRead(BaseModel):
    usernames: list[str]


class ProfilesSourceUpdate(BaseModel):
    usernames: list[str]


class ScrapeProfileRead(BaseModel):
    id: int
    username: str
    category: Optional[str] = None
    grade: Optional[str] = None
    position: int
    profile_pic_url: Optional[str] = None

    model_config = {"from_attributes": True}


class ScrapeProfileCreate(BaseModel):
    username: str
    category: Optional[str] = None
    grade: Optional[str] = None


class ScrapeProfileBulkCreate(BaseModel):
    profiles: list[ScrapeProfileCreate]


class ScrapeProfileBulkResult(BaseModel):
    created: list[ScrapeProfileRead]
    skipped_existing: list[str] = []


class ScrapeProfileUpdate(BaseModel):
    username: Optional[str] = None
    category: Optional[str] = None
    grade: Optional[str] = None


class ScrapeDbUpdateStatus(BaseModel):
    posts_rows: int = 0
    profile_snapshots_rows: int = 0
    profiles_touched: int = 0
    missing_usernames: list[str] = []


class ScrapeProfileFailureRead(BaseModel):
    username: str
    attempt_count: int = 0
    error_message: Optional[str] = None
    failure_category: str = "unknown"
    retryable: bool = False
    retries_left: int = 0


class ScrapeProfileAttemptRead(BaseModel):
    username: str
    status: str
    attempt_count: int = 0


class ScrapeProfileProgressRead(BaseModel):
    total_profiles: int = 0
    completed_count: int = 0
    pending_count: int = 0
    failed_count: int = 0
    retryable_failed_count: int = 0
    terminal_failed_count: int = 0
    running_count: int = 0
    completed_profiles: list[str] = []
    pending_profiles: list[str] = []
    failed_profiles: list[ScrapeProfileFailureRead] = []
    zero_posts_profiles: list[str] = []
    profile_attempts: list[ScrapeProfileAttemptRead] = []
    server_failure_message: Optional[str] = None


class ScrapeProfileProgressRowRead(BaseModel):
    username: str
    status: str
    attempt_count: int = 0
    items_fetched: int = 0
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    last_checkpoint_at: Optional[datetime] = None


class ScrapeProfileProgressListResponse(BaseModel):
    items: list[ScrapeProfileProgressRowRead]
    total: int
    limit: int
    offset: int


class ScrapeStatusRead(BaseModel):
    run: Optional[ScrapeRunRead] = None
    progress_pct: int = 0
    db_updates: ScrapeDbUpdateStatus = ScrapeDbUpdateStatus()
    profile_progress: ScrapeProfileProgressRead = ScrapeProfileProgressRead()
    resume_detected: bool = False
    logs: list[str] = []


class CompareSummaryRead(BaseModel):
    run_a_profile_snapshot_rows: int = 0
    run_b_profile_snapshot_rows: int = 0
    run_a_latest_posts_rows: int = 0
    run_b_latest_posts_rows: int = 0
    common_profiles: int = 0
    new_profiles: int = 0
    missing_profiles: int = 0
    net_followers_delta: int = 0
    common_latest_posts: int = 0
    new_latest_posts: int = 0
    missing_latest_posts: int = 0
    net_likes_delta: int = 0


class ProfileDeltaRead(BaseModel):
    profile_id: str
    followers_run_a: int | None = None
    followers_run_b: int | None = None
    follows_run_a: int | None = None
    follows_run_b: int | None = None
    posts_run_a: int | None = None
    posts_run_b: int | None = None
    followers_delta: int = 0
    follows_delta: int = 0
    posts_delta: int = 0
    change_type: Literal["common", "new", "missing"]


class LatestPostDeltaRead(BaseModel):
    profile_id: str
    owner_username: str | None = None
    url: str
    likes_run_a: int | None = None
    likes_run_b: int | None = None
    comments_run_a: int | None = None
    comments_run_b: int | None = None
    views_run_a: int | None = None
    views_run_b: int | None = None
    likes_delta: int = 0
    comments_delta: int = 0
    views_delta: int = 0
    change_type: Literal["common", "new", "missing"]


class InsightRead(BaseModel):
    title: str
    value: str
    detail: str
    tone: Literal["positive", "negative", "neutral"] = "neutral"


class RunComparisonRead(BaseModel):
    run_a: ScrapeRunRead
    run_b: ScrapeRunRead
    summary: CompareSummaryRead
    profile_deltas: list[ProfileDeltaRead]
    latest_post_deltas: list[LatestPostDeltaRead]
    insights: list[InsightRead]
