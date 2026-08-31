import { API_URL } from "../config"
import type {
  WisdomWarrior,
  WisdomWarriorBulkResult,
  WisdomWarriorCreate,
  WisdomWarriorUpdate,
} from "../types/wisdomWarrior"

const BASE = `${API_URL}/api/scrape/wisdom-warriors`
const ANALYTICS_BASE = `${API_URL}/api/analytics/wisdom-warriors/monthly-views`
const SNAPSHOT_RUNS_BASE = `${API_URL}/api/analytics/wisdom-warriors/snapshot-runs`

export interface WisdomWarriorSnapshotRun {
  run_id: number
  scraped_at: string
}

export interface WisdomWarriorMonthlyView {
  username: string
  month: string
  total_views: number
  matched_hashtags: string[]
  matched_mentions: string[]
  matched_tagged_users: string[]
}

export interface WisdomWarriorMonthlyViewsQuery {
  month: string
  applyFilters: boolean
  snapshotRunId?: number
  category?: string
  hashtags?: string[]
  mentions?: string[]
  taggedUsers?: string[]
  keywords?: string[]
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text || res.statusText)
  }
  if (res.status === 204) return undefined as unknown as T
  return res.json()
}

export const fetchWisdomWarriors = (): Promise<WisdomWarrior[]> =>
  fetch(BASE).then(r => handleResponse<WisdomWarrior[]>(r))

export const createWisdomWarrior = (body: WisdomWarriorCreate): Promise<WisdomWarrior> =>
  fetch(BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(r => handleResponse<WisdomWarrior>(r))

export const createWisdomWarriorsBulk = (profiles: WisdomWarriorCreate[]): Promise<WisdomWarriorBulkResult> =>
  fetch(`${BASE}/bulk`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profiles }),
  }).then(r => handleResponse<WisdomWarriorBulkResult>(r))

export const updateWisdomWarrior = (id: number, body: WisdomWarriorUpdate): Promise<WisdomWarrior> =>
  fetch(`${BASE}/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(r => handleResponse<WisdomWarrior>(r))

export const deleteWisdomWarrior = (id: number): Promise<void> =>
  fetch(`${BASE}/${id}`, { method: "DELETE" }).then(r => handleResponse<void>(r))

export const fetchWisdomWarriorsMonthlyViews = (query: WisdomWarriorMonthlyViewsQuery): Promise<WisdomWarriorMonthlyView[]> => {
  const qs = new URLSearchParams()
  qs.set("month", query.month)
  qs.set("apply_filters", String(query.applyFilters))
  if (typeof query.snapshotRunId === "number") qs.set("snapshot_run_id", String(query.snapshotRunId))
  if (query.category) qs.set("category", query.category)
  for (const value of query.hashtags ?? []) qs.append("hashtags", value)
  for (const value of query.mentions ?? []) qs.append("mentions", value)
  for (const value of query.taggedUsers ?? []) qs.append("tagged_users", value)
  for (const value of query.keywords ?? []) qs.append("keywords", value)
  return fetch(`${ANALYTICS_BASE}?${qs.toString()}`).then(r => handleResponse<WisdomWarriorMonthlyView[]>(r))
}

export const fetchWisdomWarriorsSnapshotRuns = (): Promise<WisdomWarriorSnapshotRun[]> =>
  fetch(`${SNAPSHOT_RUNS_BASE}?limit=100`).then(r => handleResponse<WisdomWarriorSnapshotRun[]>(r))

export interface GoogleSheetsSyncItem {
  channel_id: string
  creator_name: string
  username: string
  instagram_url: string
  raw_input: string
  grade: string
  category: string
  tab_name: string
  case_type: "NEW_CHANNEL" | "HANDLE_CHANGED" | "LINK_INVALID" | "CHANNEL_DELETED" | "ALREADY_TRACKED"
  status_label: string
  status_color: "green" | "yellow" | "red" | "gray"
  can_add: boolean
}

export interface GoogleSheetsSyncResponse {
  summary: {
    total_rows_scanned: number
    new_channels: number
    handle_changed: number
    link_invalid: number
    channel_deleted: number
    already_tracked: number
  }
  items: GoogleSheetsSyncItem[]
}

export const fetchGoogleSheetsSyncPreview = (source: "dedicated" | "ihi" | "leads" = "dedicated"): Promise<GoogleSheetsSyncResponse> =>
  fetch(`${API_URL}/api/scrape/wisdom-warriors/sync/preview?source=${source}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source }),
  }).then(r => handleResponse<GoogleSheetsSyncResponse>(r))

export const applyGoogleSheetsSync = (
  channelsToAdd: Array<{ username: string; grade: string; category: string }>,
  handlesToUpdate?: Array<{ profile_id: number; new_username: string }>
): Promise<{ status: string; added_count: number; updated_count: number }> =>
  fetch(`${API_URL}/api/scrape/wisdom-warriors/sync/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      channels_to_add: channelsToAdd,
      handles_to_update: handlesToUpdate ?? [],
    }),
  }).then(r => handleResponse<{ status: string; added_count: number; updated_count: number }>(r))
