import { API_URL } from "../config"
import type { RunComparison, ScrapeRun } from "../types/schedule"

export interface ScrapeRequest {
  scraper_type: string
  usernames?: string[]
  batch_mode?: boolean
  results_limit?: number
  only_posts_newer_than?: string
  date_from?: string
  date_to?: string
  data_detail_level?: "basicData" | "detailedData"
  enable_embeddings?: boolean
  apify_token?: string
}

export interface CombinedScrapeRequest {
  usernames?: string[]
  batch_mode?: boolean
  results_limit?: number
  only_posts_newer_than?: string
  date_from?: string
  date_to?: string
  data_detail_level?: "basicData" | "detailedData"
  enable_embeddings?: boolean
  apify_token?: string
}

export interface ScrapeStartResponse {
  status: string
  profiles_count: number
  run_id: number
  action?: string
}

export interface HandleValidationItem {
  submitted_handle: string
  normalized_handle: string
  status: "FOUND" | "NOT_FOUND" | "ERROR"
  instagram_id?: string | null
  current_handle?: string | null
  source?: "database" | "apify_lookup" | null
  instagram_url: string
  error_message?: string | null
}

export interface ValidateHandlesResponse {
  total: number
  found_count: number
  not_found_count: number
  error_count: number
  results: HandleValidationItem[]
}

export interface ProfilesSourceResponse {
  usernames: string[]
}

export interface ScrapeDbUpdateStatus {
  posts_rows: number
  profile_snapshots_rows: number
  profiles_touched: number
  missing_usernames: string[]
}

export interface ScrapeProfileFailure {
  username: string
  attempt_count: number
  error_message?: string
  failure_category: string
  retryable: boolean
  retries_left: number
}

export interface ScrapeProfileAttempt {
  username: string
  status: string
  attempt_count: number
}

export interface ScrapeProfileProgressRow {
  username: string
  status: string
  attempt_count: number
  items_fetched: number
  error_message?: string
  started_at?: string
  finished_at?: string
  last_checkpoint_at?: string
}

export interface ScrapeProfileProgressListResponse {
  items: ScrapeProfileProgressRow[]
  total: number
  limit: number
  offset: number
}

export interface ScrapeProfileProgress {
  total_profiles: number
  completed_count: number
  pending_count: number
  failed_count: number
  retryable_failed_count: number
  terminal_failed_count: number
  running_count: number
  completed_profiles: string[]
  pending_profiles: string[]
  failed_profiles: ScrapeProfileFailure[]
  zero_posts_profiles: string[]
  profile_attempts: ScrapeProfileAttempt[]
  server_failure_message?: string
}

export interface ScrapeStatusResponse {
  run: ScrapeRun | null
  progress_pct: number
  db_updates: ScrapeDbUpdateStatus
  profile_progress?: ScrapeProfileProgress
  resume_detected?: boolean
  logs: string[]
}

export interface ApifyRefetchResponse {
  run_id: number
  stage: "posts" | "profiles"
  apify_run_id: string
  apify_dataset_id: string
  apify_status?: string
  items_count: number
  logs_count: number
  status: string
}

export const triggerScrape = (body: ScrapeRequest): Promise<ScrapeStartResponse> =>
  fetch(`${API_URL}/api/scrape/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(r => r.json())

export const validateHandles = (handles: string[], apifyToken?: string): Promise<ValidateHandlesResponse> =>
  fetch(`${API_URL}/api/scrape/validate-handles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ handles, apify_token: apifyToken }),
  }).then(r => r.json())

export const triggerCombinedScrape = (body: CombinedScrapeRequest): Promise<ScrapeStartResponse> =>
  fetch(`${API_URL}/api/scrape/run/combined`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(r => r.json())

export const fetchRuns = (params: Record<string, string | number | undefined> = {}): Promise<{ items: ScrapeRun[]; total: number }> => {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined) qs.set(k, String(v))
  }
  return fetch(`${API_URL}/api/scrape/runs?${qs}`).then(r => r.json())
}

export const fetchProfilesSource = (): Promise<ProfilesSourceResponse> =>
  fetch(`${API_URL}/api/scrape/profiles-source`).then(r => r.json())

export const updateProfilesSource = (usernames: string[]): Promise<ProfilesSourceResponse> =>
  fetch(`${API_URL}/api/scrape/profiles-source`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ usernames }),
  }).then(r => r.json())

export const fetchScrapeStatus = (runId?: number): Promise<ScrapeStatusResponse> => {
  const qs = new URLSearchParams()
  if (runId !== undefined) qs.set("run_id", String(runId))
  return fetch(`${API_URL}/api/scrape/status?${qs}`).then(r => r.json())
}

export const fetchRunProfileProgress = (
  runId: number,
  params: Record<string, string | number | undefined> = {},
): Promise<ScrapeProfileProgressListResponse> => {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") qs.set(k, String(v))
  }
  return fetch(`${API_URL}/api/scrape/runs/${runId}/profile-progress?${qs.toString()}`).then(r => r.json())
}

export const skipEmbedding = (runId: number): Promise<ScrapeRun> =>
  fetch(`${API_URL}/api/scrape/runs/${runId}/skip-embedding`, { method: "PATCH" }).then(r => {
    if (!r.ok) return r.json().then(e => Promise.reject(new Error(e.detail ?? "Failed")))
    return r.json()
  })

export const resumePendingPosts = (runId: number): Promise<ScrapeStartResponse> =>
  fetch(`${API_URL}/api/scrape/runs/${runId}/resume-pending-posts`, {
    method: "POST",
  }).then(async r => {
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: "Failed to resume pending profiles" }))
      throw new Error(err.detail ?? "Failed to resume pending profiles")
    }
    return r.json()
  })

export const refetchRunFromApify = (
  runId: number,
  stage: "posts" | "profiles",
  includeLogs = true,
): Promise<ApifyRefetchResponse> =>
  fetch(`${API_URL}/api/scrape/runs/${runId}/apify-refetch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stage, include_logs: includeLogs }),
  }).then(async r => {
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: "Failed to refetch from Apify" }))
      throw new Error(err.detail ?? "Failed to refetch from Apify")
    }
    return r.json()
  })

export const fetchRunComparison = (
  runAId: number,
  runBId: number,
  profileLimit = 50,
  latestPostLimit = 50,
): Promise<RunComparison> => {
  const qs = new URLSearchParams({
    run_a_id: String(runAId),
    run_b_id: String(runBId),
    profile_limit: String(profileLimit),
    latest_post_limit: String(latestPostLimit),
  })
  return fetch(`${API_URL}/api/scrape/runs/compare?${qs}`).then(async r => {
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: "Failed to compare runs" }))
      throw new Error(err.detail ?? "Failed to compare runs")
    }
    return r.json()
  })
}
