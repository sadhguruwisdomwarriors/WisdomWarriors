import { useEffect, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { fetchProfilesSource, fetchRunProfileProgress, fetchScrapeStatus, refetchRunFromApify, resumePendingPosts, triggerScrape, validateHandles, type ValidateHandlesResponse } from "../../api/scrape"
import { RecentRunsTable } from "../Dashboard/RecentRunsTable"
import type { ScrapeRun } from "../../types/schedule"

function parseUsernames(value: string) {
  return Array.from(new Set(value.split(/\r?\n/).map(line => line.trim()).filter(Boolean)))
}

const APIFY_TOKEN_STORAGE_KEY = "wisdom-warriors.apify-token"
const MS_PER_DAY = 24 * 60 * 60 * 1000

function getDerivedDaysValue(daysValue: string, dateFrom: string) {
  const trimmed = daysValue.trim()
  if (trimmed) return trimmed
  if (!dateFrom) return ""

  const from = new Date(`${dateFrom}T00:00:00`)
  if (Number.isNaN(from.getTime())) return ""

  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  return String(Math.max(0, Math.ceil((today.getTime() - from.getTime()) / MS_PER_DAY)))
}

export default function ScrapePage() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ["profiles-source"], queryFn: fetchProfilesSource })
  const [profilesText, setProfilesText] = useState("")
  const [activeRunId, setActiveRunId] = useState<number | undefined>(undefined)
  const [liveLogs, setLiveLogs] = useState<string[]>([])
  const [showPostsModal, setShowPostsModal] = useState(false)
  const [resultsLimit, setResultsLimit] = useState(100)
  const [newerThanValue, setNewerThanValue] = useState("")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")
  const [dataDetailLevel, setDataDetailLevel] = useState<"basicData" | "detailedData">("detailedData")
  const [batchMode, setBatchMode] = useState(false)
  const [enableEmbeddings, setEnableEmbeddings] = useState(false)
  const [apifyToken, setApifyToken] = useState("")
  const [isScrapeLocked, setIsScrapeLocked] = useState(false)
  const [refetchRunIdText, setRefetchRunIdText] = useState("")
  const [includeRefetchLogs, setIncludeRefetchLogs] = useState(true)
  const [refetchStage, setRefetchStage] = useState<{ runId: number; stage: "posts" | "profiles" } | null>(null)
  
  // Pre-scrape Instagram ID Validation state
  const [isValidating, setIsValidating] = useState(false)
  const [validationData, setValidationData] = useState<ValidateHandlesResponse | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)

  const usernames = parseUsernames(profilesText)

  const handleValidateHandles = async () => {
    if (usernames.length === 0 || isValidating || isScrapeBusy) return
    setIsValidating(true)
    setValidationError(null)
    try {
      const res = await validateHandles(usernames, apifyToken.trim() || undefined)
      setValidationData(res)
    } catch (err) {
      setValidationError(err instanceof Error ? err.message : "Validation failed")
    } finally {
      setIsValidating(false)
    }
  }

  const handleResetValidation = () => {
    setValidationData(null)
    setValidationError(null)
  }

  const resolvedHandles = validationData
    ? validationData.results.filter(r => r.status === "FOUND").map(r => r.current_handle || r.normalized_handle)
    : usernames

  const { data: statusData } = useQuery({
    queryKey: ["scrape-status", activeRunId],
    queryFn: () => fetchScrapeStatus(activeRunId),
    refetchInterval: 2000,
  })

  const { data: runProfileProgressData } = useQuery({
    queryKey: ["run-profile-progress", activeRunId],
    queryFn: () => fetchRunProfileProgress(activeRunId as number, { limit: 500, offset: 0 }),
    enabled: typeof activeRunId === "number",
    refetchInterval: 2000,
  })

  const secondPostScraperCount = statusData?.run?.scraper_type === "posts"
    ? statusData.run.items_fetched
    : (statusData?.db_updates.posts_rows ?? 0)
  const profileProgress = statusData?.profile_progress
  const profileRows = runProfileProgressData?.items ?? []
  const completedProfiles = profileRows.filter(row => row.status === "success").map(row => row.username)
  const pendingProfiles = profileRows.filter(row => row.status === "pending").map(row => row.username)
  const failedProfiles = profileRows.filter(row => row.status === "failed")
  const failedProfilesDetailed = profileProgress?.failed_profiles ?? []
  const zeroPostsProfiles = profileRows.filter(row => row.status === "success" && row.items_fetched === 0).map(row => row.username)
  const currentRunStatus = statusData?.run?.status
  const isScrapeBusy = isScrapeLocked || currentRunStatus === "running"
  const hasInvalidDateRange = Boolean(dateFrom && dateTo && dateFrom > dateTo)
  const effectiveDaysValue = getDerivedDaysValue(newerThanValue, dateFrom)
  const pendingProfileCount = profileProgress?.pending_count ?? pendingProfiles.length
  const retryableFailedCount = profileProgress?.retryable_failed_count
    ?? failedProfilesDetailed.filter(profile => profile.retryable).length
  const terminalFailedCount = profileProgress?.terminal_failed_count
    ?? failedProfilesDetailed.filter(profile => !profile.retryable).length
  const remainingRetryableCount = pendingProfileCount + retryableFailedCount
  const canResumeRemaining =
    typeof activeRunId === "number"
    && (currentRunStatus === "completed" || currentRunStatus === "failed")
    && remainingRetryableCount > 0
    && !isScrapeBusy
  const parsedRefetchRunId = Number(refetchRunIdText)
  const isRefetchRunIdValid = Number.isInteger(parsedRefetchRunId) && parsedRefetchRunId > 0

  useEffect(() => {
    if (!statusData?.run) return
    setActiveRunId(prev => prev ?? statusData.run?.id)
  }, [statusData])

  useEffect(() => {
    if (!activeRunId) return
    setRefetchRunIdText(prev => prev.trim() ? prev : String(activeRunId))
  }, [activeRunId])

  useEffect(() => {
    if (!statusData) return
    const timestamp = new Date().toLocaleTimeString()
    setLiveLogs(prev => {
      const next = [...prev]
      for (const line of statusData.logs) {
        const alreadyExists = next.some(existing => existing.endsWith(`] ${line}`))
        if (!alreadyExists) next.push(`[${timestamp}] ${line}`)
      }
      return next.slice(-120)
    })
  }, [statusData])

  useEffect(() => {
    if (data) {
      setProfilesText(data.usernames.join("\n"))
    }
  }, [data])

  useEffect(() => {
    const storedToken = window.localStorage.getItem(APIFY_TOKEN_STORAGE_KEY)
    if (storedToken) setApifyToken(storedToken)
  }, [])

  useEffect(() => {
    if (!isScrapeLocked) return
    if (currentRunStatus === "completed" || currentRunStatus === "failed") {
      setIsScrapeLocked(false)
    }
  }, [currentRunStatus, isScrapeLocked])

  useEffect(() => {
    const trimmed = apifyToken.trim()
    if (trimmed) {
      window.localStorage.setItem(APIFY_TOKEN_STORAGE_KEY, trimmed)
    } else {
      window.localStorage.removeItem(APIFY_TOKEN_STORAGE_KEY)
    }
  }, [apifyToken])

  const handleCombinedScrape = async () => {
    const targetUsernames = validationData ? resolvedHandles : usernames
    if (isScrapeBusy || targetUsernames.length === 0 || hasInvalidDateRange) return

    const startedAt = new Date().toLocaleTimeString()
    setIsScrapeLocked(true)
    setLiveLogs([
      `[${startedAt}] Starting posts scrape for ${targetUsernames.length} resolved profile(s)...`,
      `[${startedAt}] Submitting ${targetUsernames.length} profile(s) for scraping...`,
    ])
    try {
      const req: Parameters<typeof triggerScrape>[0] = {
        usernames: targetUsernames,
        scraper_type: "posts",
        batch_mode: batchMode,
        results_limit: resultsLimit,
        data_detail_level: dataDetailLevel,
        enable_embeddings: enableEmbeddings,
      }
      if (effectiveDaysValue) {
        req.only_posts_newer_than = effectiveDaysValue
      }
      if (dateFrom) {
        req.date_from = dateFrom
      }
      if (dateTo) {
        req.date_to = dateTo
      }
      if (apifyToken.trim()) {
        req.apify_token = apifyToken.trim()
      }
      const started = await triggerScrape(req)
      setActiveRunId(started.run_id)
      setShowPostsModal(false)
      setLiveLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Tracking run #${started.run_id}.`].slice(-120))
      qc.invalidateQueries({ queryKey: ["scrape-status", started.run_id] })
      qc.invalidateQueries({ queryKey: ["runs"] })
    } catch {
      setIsScrapeLocked(false)
      setLiveLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Error while starting scrape.`].slice(-120))
    }
  }

  const handleResumePendingPosts = async () => {
    if (!activeRunId || !canResumeRemaining) return
    setIsScrapeLocked(true)
    setLiveLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Resuming pending/failed profiles in run #${activeRunId}...`].slice(-120))
    try {
      const resumed = await resumePendingPosts(activeRunId)
      setActiveRunId(resumed.run_id)
      qc.invalidateQueries({ queryKey: ["scrape-status", resumed.run_id] })
      qc.invalidateQueries({ queryKey: ["run-profile-progress", resumed.run_id] })
      qc.invalidateQueries({ queryKey: ["runs"] })
      setLiveLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Pending/failed profile scrape resumed for run #${resumed.run_id}.`].slice(-120))
    } catch (error) {
      setIsScrapeLocked(false)
      const message = error instanceof Error ? error.message : "Failed to resume pending profiles"
      setLiveLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${message}`].slice(-120))
    }
  }

  const handleRefetchExistingRun = async (stage: "posts" | "profiles", runIdOverride?: number) => {
    const runId = typeof runIdOverride === "number" ? runIdOverride : parsedRefetchRunId
    if (isScrapeBusy || refetchStage !== null || !Number.isInteger(runId) || runId <= 0) return
    setRefetchRunIdText(String(runId))
    setRefetchStage({ runId, stage })
    setLiveLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Refetching ${stage} stage from Apify for run #${runId}...`].slice(-120))
    try {
      const result = await refetchRunFromApify(runId, stage, includeRefetchLogs)
      setActiveRunId(result.run_id)
      qc.invalidateQueries({ queryKey: ["scrape-status", result.run_id] })
      qc.invalidateQueries({ queryKey: ["run-profile-progress", result.run_id] })
      qc.invalidateQueries({ queryKey: ["runs"] })
      setLiveLogs(prev => [
        ...prev,
        `[${new Date().toLocaleTimeString()}] Refetch complete for run #${result.run_id} (${stage}): ${result.items_count} item(s) replayed across stored Apify runs.`,
      ].slice(-120))
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to refetch existing run"
      setLiveLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${message}`].slice(-120))
    } finally {
      setRefetchStage(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Wisdom Warriors Scraper</h1>
          <p className="text-sm text-gray-400 mt-1">Manage the usernames to scrape and monitor each scrape run.</p>
        </div>
      </div>
      {showPostsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-gray-700 bg-gray-900 p-6 shadow-2xl space-y-5">
            <div>
              <h2 className="text-base font-semibold text-gray-100">Scrape Wisdom Warriors</h2>
              <p className="text-xs text-gray-400 mt-1">Configure the posts scraper that fetches posts for each listed profile.</p>
            </div>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-300">Max posts per profile <span className="text-red-400">*</span></label>
                <input
                  type="number"
                  min={1}
                  max={500}
                  value={resultsLimit}
                  onChange={e => setResultsLimit(Number(e.target.value))}
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 outline-none focus:border-blue-500"
                />
              </div>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-gray-300">Days (optional)</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min={0}
                      placeholder="e.g. 15"
                      value={newerThanValue}
                      onChange={e => setNewerThanValue(e.target.value)}
                      className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 outline-none focus:border-blue-500"
                    />
                    {newerThanValue !== "" && (
                      <button
                        onClick={() => setNewerThanValue("")}
                        className="text-gray-500 hover:text-gray-300 text-sm leading-none px-1"
                        title="Clear"
                      >✕</button>
                    )}
                  </div>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-gray-300">From</label>
                    <input
                      type="date"
                      value={dateFrom}
                      onChange={e => setDateFrom(e.target.value)}
                      className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 outline-none focus:border-blue-500"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-gray-300">To</label>
                    <input
                      type="date"
                      value={dateTo}
                      min={dateFrom || undefined}
                      onChange={e => setDateTo(e.target.value)}
                      className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 outline-none focus:border-blue-500"
                    />
                  </div>
                </div>
                <p className="text-xs text-gray-500">
                  Use Days, From, To, or both. The date range is applied exactly after scraping, and Days limits the fetch window.
                </p>
                {effectiveDaysValue !== "" && (
                  <p className="text-xs text-gray-500">
                    Sent as: <span className="font-mono">{effectiveDaysValue} days</span>
                  </p>
                )}
                {hasInvalidDateRange && (
                  <p className="text-xs text-red-400">The To date must be on or after the From date.</p>
                )}
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-300">Data detail level <span className="text-red-400">*</span></label>
                <select
                  value={dataDetailLevel}
                  onChange={e => setDataDetailLevel(e.target.value as "basicData" | "detailedData")}
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 outline-none focus:border-blue-500"
                >
                  <option value="basicData">Basic data (faster, cheaper)</option>
                  <option value="detailedData">Detailed data (includes video play count, alt text, music info)</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-300">APIFY token override (optional)</label>
                <input
                  type="password"
                  placeholder="Leave blank to use the backend default token"
                  value={apifyToken}
                  onChange={e => setApifyToken(e.target.value)}
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 outline-none focus:border-blue-500"
                />
                <p className="text-xs text-gray-500">
                  This value is stored only in this browser for Admin convenience and is used for manual Wisdom Warriors scrapes.
                </p>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-300">Post scraping mode</label>
                <select
                  value={batchMode ? "batch" : "single"}
                  onChange={e => setBatchMode(e.target.value === "batch")}
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 outline-none focus:border-blue-500"
                >
                  <option value="single">Scrape posts one profile at a time (safer)</option>
                  <option value="batch">Scrape posts for all profiles in one batch (faster)</option>
                </select>
              </div>
              <label className="flex items-start gap-3 rounded-lg border border-gray-700 bg-gray-800/60 px-3 py-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={enableEmbeddings}
                  onChange={e => setEnableEmbeddings(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-gray-600 accent-fuchsia-500"
                />
                <span className="space-y-1">
                  <span className="block text-xs font-medium text-gray-300">Generate embeddings after scrape</span>
                  <span className="block text-xs text-gray-500">Turn this off to scrape and store data without running the embedding/indexing step.</span>
                </span>
              </label>
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <button
                onClick={() => setShowPostsModal(false)}
                className="px-4 py-2 text-sm rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCombinedScrape}
                disabled={!resultsLimit || resultsLimit < 1 || isScrapeBusy || hasInvalidDateRange}
                className="px-4 py-2 text-sm rounded-lg bg-gradient-to-r from-fuchsia-600 to-blue-600 hover:from-fuchsia-500 hover:to-blue-500 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
              >
                {isScrapeBusy ? "Scrape in Progress…" : "Scrape Now"}
              </button>
            </div>
          </div>
        </div>
      )}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-gray-200">Profiles To Scrape</h2>
            <p className="text-xs text-gray-400 mt-1">Edit the Instagram usernames used by manual scrapes. One profile per line.</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400">{usernames.length} profiles</span>
          </div>
        </div>
        <textarea
          value={profilesText}
          onChange={e => setProfilesText(e.target.value)}
          className="w-full min-h-72 rounded-xl border border-gray-800 bg-gray-950 px-4 py-3 text-sm text-gray-100 outline-none focus:border-purple-600"
          placeholder="Enter one Instagram username per line"
        />
        <div className="flex items-center justify-between text-xs text-gray-400">
          <span>
            {isScrapeBusy
              ? "Scrape in progress. The button will re-enable after the selected stages finish and the database updates complete."
              : "The listed usernames are used by the posts scraper to fetch posts per profile."}
          </span>
          <span>Removes duplicates automatically.</span>
        </div>
        <div className="flex justify-center gap-3 pt-2">
          <button
            onClick={handleValidateHandles}
            className="px-4 py-2 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-semibold flex items-center gap-2"
            disabled={usernames.length === 0 || isScrapeBusy || isValidating}
          >
            {isValidating ? "🔍 Validating Instagram IDs…" : "🔍 Check Instagram IDs"}
          </button>
          <button
            onClick={() => setShowPostsModal(true)}
            className="px-4 py-2 text-xs bg-fuchsia-600 hover:bg-fuchsia-500 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-semibold flex items-center gap-2"
            disabled={usernames.length === 0 || isScrapeBusy || (validationData !== null && resolvedHandles.length === 0)}
          >
            {isScrapeBusy ? "🧙 Scrape in Progress…" : `🧙 Scrape Wisdom Warriors (${validationData ? resolvedHandles.length : usernames.length})`}
          </button>
        </div>
      </div>

      {/* Validation State 2: Loading UI */}
      {isValidating && (
        <div className="rounded-xl border border-blue-800 bg-blue-950/40 p-5 space-y-3 animate-pulse">
          <div className="flex items-center gap-3">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
            <span className="text-sm font-semibold text-blue-200">Checking & Resolving Instagram IDs...</span>
          </div>
          <p className="text-xs text-blue-300">Searching local database first, then resolving missing IDs via Instagram lookup. Please wait...</p>
        </div>
      )}

      {validationError && (
        <div className="rounded-xl border border-red-800 bg-red-950/40 p-4 text-xs text-red-300">
          Validation error: {validationError}
        </div>
      )}

      {/* Validation State 3 & 4: Validation Summary & Itemized Checked Profiles */}
      {validationData && !isValidating && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-gray-800 pb-4">
            <div>
              <h2 className="text-base font-bold text-gray-100 flex items-center gap-2">
                <span>🔍 Instagram ID Validation Complete</span>
              </h2>
              <p className="text-xs text-gray-400 mt-0.5">
                Instagram IDs resolved for submitted handles before scraping begins.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={handleResetValidation}
                className="px-3 py-1.5 text-xs rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 transition-colors font-medium"
              >
                ✏️ Re-paste Handles
              </button>
              <button
                onClick={() => setShowPostsModal(true)}
                disabled={validationData.found_count === 0 || isScrapeBusy}
                className="px-4 py-1.5 text-xs bg-gradient-to-r from-fuchsia-600 to-blue-600 hover:from-fuchsia-500 hover:to-blue-500 text-white rounded-lg transition-colors font-bold disabled:opacity-50 disabled:cursor-not-allowed"
              >
                🚀 Start Scraping ({validationData.found_count} Ready)
              </button>
            </div>
          </div>

          {/* Metrics */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
              <p className="text-xs text-gray-400">Total Handles Submitted</p>
              <p className="text-lg font-bold text-gray-100 mt-0.5">{validationData.total}</p>
            </div>
            <div className="rounded-lg border border-emerald-900/60 bg-emerald-950/30 p-3">
              <p className="text-xs text-emerald-400 font-medium">Instagram IDs Found</p>
              <p className="text-lg font-bold text-emerald-200 mt-0.5">{validationData.found_count}</p>
            </div>
            <div className="rounded-lg border border-red-900/60 bg-red-950/30 p-3">
              <p className="text-xs text-red-400 font-medium">Instagram IDs Not Found</p>
              <p className="text-lg font-bold text-red-200 mt-0.5">{validationData.not_found_count + validationData.error_count}</p>
            </div>
          </div>

          {/* Unresolved Banner */}
          {validationData.not_found_count + validationData.error_count > 0 ? (
            <div className="rounded-lg border border-amber-900/80 bg-amber-950/40 p-3 text-xs text-amber-200 space-y-1">
              <p className="font-semibold">⚠️ {validationData.not_found_count + validationData.error_count} handle(s) could not be associated with an Instagram ID:</p>
              <p className="text-amber-300/80">
                Click "Start Scraping" to scrape the {validationData.found_count} resolved account(s) and skip unresolved ones, or click "Re-paste Handles" to return and edit the handles list.
              </p>
            </div>
          ) : (
            <div className="rounded-lg border border-emerald-900/80 bg-emerald-950/40 p-3 text-xs text-emerald-200 font-medium">
              ✅ All {validationData.total} Instagram IDs have been successfully resolved and are ready for scraping!
            </div>
          )}

          {/* Checked Profiles List with Clickable Links */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-gray-300">Checked Profiles & Clickable Links</h3>
            <div className="max-h-72 overflow-y-auto rounded-lg border border-gray-800 bg-gray-950 divide-y divide-gray-800/60">
              {validationData.results.map((item, idx) => (
                <div key={`${item.submitted_handle}-${idx}`} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2 text-xs">
                  <div className="flex items-center gap-3 min-w-48">
                    <span className="font-mono text-gray-400 text-[11px] w-6">{idx + 1}.</span>
                    <div>
                      <div className="font-medium text-gray-200 flex items-center gap-2">
                        <span>@{item.submitted_handle}</span>
                        {item.current_handle && item.current_handle.toLowerCase() !== item.submitted_handle.toLowerCase() && (
                          <span className="text-[10px] text-purple-300 bg-purple-950/80 border border-purple-800 rounded px-1.5 py-0.5">
                            Renamed to @{item.current_handle}
                          </span>
                        )}
                      </div>
                      {item.instagram_id && (
                        <div className="text-[11px] text-gray-500 font-mono">
                          ID: {item.instagram_id} ({item.source === "database" ? "DB Match" : "Live Lookup"})
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-4">
                    {/* Clickable link */}
                    <a
                      href={item.instagram_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300 hover:underline"
                    >
                      <span>View on Instagram</span>
                      <span className="text-[10px]">↗</span>
                    </a>

                    {/* Status Badge */}
                    {item.status === "FOUND" ? (
                      <span className="inline-flex items-center rounded-full border border-emerald-800 bg-emerald-950/80 px-2.5 py-0.5 text-[11px] font-medium text-emerald-300">
                        ID Found
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded-full border border-red-800 bg-red-950/80 px-2.5 py-0.5 text-[11px] font-medium text-red-300" title={item.error_message || undefined}>
                        ID Not Found
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-gray-200">Database Update Status</h2>
            {statusData?.resume_detected && (
              <span className="inline-flex items-center rounded-full border border-amber-700 bg-amber-900/40 px-2 py-0.5 text-xs font-medium text-amber-200">
                Resumed after restart
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400 mt-1">Rows updated for the selected run.</p>
          {statusData?.run && (
            <div className="mt-3 grid grid-cols-1 gap-2 text-[11px] text-gray-300 sm:grid-cols-2">
              <div className="rounded-md border border-gray-800 bg-gray-950/70 px-2.5 py-2">
                <p className="text-gray-400">Apify Posts</p>
                <p>Run: {statusData.run.apify_posts_run_id ?? "-"}</p>
                <p>Dataset: {statusData.run.apify_posts_dataset_id ?? "-"}</p>
              </div>
              <div className="rounded-md border border-gray-800 bg-gray-950/70 px-2.5 py-2">
                <p className="text-gray-400">Apify Profiles</p>
                <p>Run: {statusData.run.apify_profiles_run_id ?? "-"}</p>
                <p>Dataset: {statusData.run.apify_profiles_dataset_id ?? "-"}</p>
              </div>
            </div>
          )}
          {canResumeRemaining && (
            <div className="mt-3">
              <button
                onClick={handleResumePendingPosts}
                className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-amber-500"
              >
                Scrape Pending/Failed Wisdom Warriors ({remainingRetryableCount})
              </button>
              {terminalFailedCount > 0 && (
                <p className="mt-2 text-[11px] text-red-300">
                  {terminalFailedCount} terminal failure(s) require manual fix and are excluded from retry.
                </p>
              )}
            </div>
          )}
          <div className="mt-3 rounded-lg border border-gray-800 bg-gray-950/60 p-3 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold text-gray-200">Refetch Existing Run From Apify</p>
                <p className="text-[11px] text-gray-500 mt-1">Use an existing internal run ID to replay stored Apify run outputs into the database.</p>
              </div>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="sm:col-span-1">
                <label className="text-[11px] text-gray-400">Internal Run ID</label>
                <input
                  type="number"
                  min={1}
                  value={refetchRunIdText}
                  onChange={e => setRefetchRunIdText(e.target.value)}
                  placeholder={activeRunId ? String(activeRunId) : "e.g. 123"}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 outline-none focus:border-blue-500"
                />
              </div>
              <div className="sm:col-span-2 flex flex-col justify-end gap-2">
                <label className="inline-flex items-center gap-2 text-[11px] text-gray-300">
                  <input
                    type="checkbox"
                    checked={includeRefetchLogs}
                    onChange={e => setIncludeRefetchLogs(e.target.checked)}
                    className="h-3.5 w-3.5 rounded border-gray-600 accent-blue-500"
                  />
                  Include raw Apify logs in run logs
                </label>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => handleRefetchExistingRun("posts")}
                    disabled={!isRefetchRunIdValid || isScrapeBusy || refetchStage !== null}
                    className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {refetchStage?.stage === "posts" && refetchStage.runId === parsedRefetchRunId ? "Refetching Posts…" : "Refetch Posts Stage"}
                  </button>
                  <button
                    onClick={() => handleRefetchExistingRun("profiles")}
                    disabled={!isRefetchRunIdValid || isScrapeBusy || refetchStage !== null}
                    className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {refetchStage?.stage === "profiles" && refetchStage.runId === parsedRefetchRunId ? "Refetching Profiles…" : "Refetch Profiles Stage"}
                  </button>
                  {!isRefetchRunIdValid && (
                    <span className="text-[11px] text-amber-300">Enter a valid run ID to enable refetch.</span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
            <p className="text-xs text-gray-400">Profiles Processed (Post Scraper)</p>
            <p className="text-lg font-semibold mt-1">{profileProgress?.completed_count ?? statusData?.db_updates.profiles_touched ?? 0}</p>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
            <p className="text-xs text-gray-400">Posts Scraped</p>
            <p className="text-lg font-semibold mt-1">{secondPostScraperCount}</p>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
            <p className="text-xs text-gray-400">Profiles Pending</p>
            <p className="text-lg font-semibold mt-1">{profileProgress?.pending_count ?? 0}</p>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
            <p className="text-xs text-gray-400">Profiles Failed</p>
            <p className="text-lg font-semibold mt-1">{profileProgress?.failed_count ?? 0}</p>
            <p className="mt-1 text-[11px] text-gray-500">
              Retryable: {retryableFailedCount} | Terminal: {terminalFailedCount}
            </p>
          </div>
        </div>
        {profileProgress?.server_failure_message && (
          <div className="rounded-lg border border-red-900 bg-red-950/30 px-3 py-2 text-sm text-red-200">
            {profileProgress.server_failure_message.replace("scrape", "post scrape")}
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-gray-400">Completed Profiles (Posts Fetched)</p>
              <p className="text-xs text-emerald-300">{profileProgress?.completed_count ?? 0}</p>
            </div>
            {profileProgress?.completed_profiles?.length ? (
              <div className="mt-3 flex max-h-32 flex-wrap gap-2 overflow-auto pr-1">
                {(completedProfiles.length ? completedProfiles : (profileProgress?.completed_profiles ?? [])).map(username => (
                  <span
                    key={username}
                    className="rounded-full border border-emerald-900 bg-emerald-950/60 px-2 py-1 text-xs text-emerald-200"
                  >
                    {username}
                  </span>
                ))}
              </div>
            ) : (
              <p className="mt-3 text-sm text-gray-500">No completed profiles yet.</p>
            )}
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-gray-400">Pending Profiles (Post Scraper)</p>
              <p className="text-xs text-amber-300">{profileProgress?.pending_count ?? 0}</p>
            </div>
            {profileProgress?.pending_profiles?.length ? (
              <div className="mt-3 flex max-h-32 flex-wrap gap-2 overflow-auto pr-1">
                {(pendingProfiles.length ? pendingProfiles : (profileProgress?.pending_profiles ?? [])).map(username => (
                  <span
                    key={username}
                    className="rounded-full border border-amber-900 bg-amber-950/60 px-2 py-1 text-xs text-amber-200"
                  >
                    {username}
                  </span>
                ))}
              </div>
            ) : (
              <p className="mt-3 text-sm text-gray-500">No pending profiles.</p>
            )}
          </div>
        </div>
        <div className="rounded-lg border border-gray-800 bg-gray-950 p-3 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-gray-400">Failed Profiles (Post Scraper)</p>
            <p className="text-xs text-red-300">{profileProgress?.failed_count ?? 0} failed</p>
          </div>
          {(failedProfiles.length ? failedProfiles.length : failedProfilesDetailed.length) ? (
            <div className="space-y-2 max-h-44 overflow-auto pr-1">
              {(failedProfilesDetailed.length ? failedProfilesDetailed : failedProfiles).map(profile => (
                <div
                  key={profile.username}
                  className="rounded-lg border border-red-900 bg-red-950/40 px-3 py-2 text-xs"
                >
                  <div className="flex items-center justify-between gap-2 text-red-200">
                    <span className="font-medium">{profile.username}</span>
                    <span>
                      attempts: {profile.attempt_count}
                      {" | "}
                      {"retryable" in profile && profile.retryable ? "retryable" : "terminal"}
                    </span>
                  </div>
                  {"failure_category" in profile && (
                    <p className="mt-1 text-red-300/90 break-words">category: {profile.failure_category}</p>
                  )}
                  {"retries_left" in profile && (
                    <p className="mt-1 text-red-300/90 break-words">retries left: {profile.retries_left}</p>
                  )}
                  {profile.error_message && (
                    <p className="mt-1 text-red-300/90 break-words">{profile.error_message}</p>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500">No failed profiles for this run.</p>
          )}
        </div>
        <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-gray-400">Profiles With 0 Posts</p>
            <p className="text-xs text-sky-300">{profileProgress?.zero_posts_profiles?.length ?? 0}</p>
          </div>
          {(zeroPostsProfiles.length ? zeroPostsProfiles.length : (profileProgress?.zero_posts_profiles?.length ?? 0)) ? (
            <div className="mt-3 flex max-h-32 flex-wrap gap-2 overflow-auto pr-1">
              {(zeroPostsProfiles.length ? zeroPostsProfiles : (profileProgress?.zero_posts_profiles ?? [])).map(username => (
                <span
                  key={username}
                  className="rounded-full border border-sky-900 bg-sky-950/40 px-2 py-1 text-xs text-sky-200"
                >
                  {username}
                </span>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-sm text-gray-500">No zero-post profiles in this run.</p>
          )}
        </div>
        <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-gray-400">Post Scraper Attempt Tracker</p>
            <p className="text-xs text-gray-300">{profileRows.length || profileProgress?.profile_attempts?.length || 0} profiles</p>
          </div>
          {(profileRows.length || profileProgress?.profile_attempts?.length) ? (
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 max-h-44 overflow-auto pr-1">
              {(profileRows.length
                ? profileRows.map(row => ({ username: row.username, status: row.status, attempt_count: row.attempt_count }))
                : (profileProgress?.profile_attempts ?? [])
              ).map(item => (
                <div key={item.username} className="rounded border border-gray-800 bg-gray-900/60 px-2 py-1.5 text-xs text-gray-200">
                  <div className="truncate font-medium">{item.username}</div>
                  <div className="mt-1 text-gray-400">{item.status} | attempts: {item.attempt_count}</div>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-sm text-gray-500">Attempt data will appear after run initialization.</p>
          )}
        </div>
        <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-gray-400">Profiles Missing in Post Results</p>
            <p className="text-xs text-red-300">{statusData?.db_updates.missing_usernames?.length ?? 0} missing</p>
          </div>
          {statusData?.db_updates.missing_usernames?.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {statusData.db_updates.missing_usernames.map(username => (
                <span
                  key={username}
                  className="rounded-full border border-red-900 bg-red-950/60 px-2 py-1 text-xs text-red-200"
                >
                  {username}
                </span>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-sm text-gray-500">No missing profiles for this run.</p>
          )}
        </div>
      </div>
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-4">
        <div>
          <h2 className="text-sm font-semibold text-gray-200">Live Logs</h2>
          <p className="text-xs text-gray-400 mt-1">Real-time run and DB update messages.</p>
        </div>
        <div className="rounded-xl border border-gray-800 bg-gray-950 px-4 py-3 text-xs text-gray-200 font-mono max-h-56 overflow-auto space-y-1">
          {liveLogs.length === 0 ? (
            <div className="text-gray-500">No logs yet. Start a scrape to stream updates.</div>
          ) : (
            liveLogs.map((line, i) => <div key={`${line}-${i}`}>{line}</div>)
          )}
        </div>
      </div>
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
        <h2 className="text-sm font-semibold text-gray-300 mb-4">Recent Scrape Runs</h2>
        <RecentRunsTable
          onSelectRun={(run: ScrapeRun) => {
            setActiveRunId(run.id)
            setRefetchRunIdText(String(run.id))
          }}
          onRefetchStage={(run: ScrapeRun, stage: "posts" | "profiles") => {
            setActiveRunId(run.id)
            setRefetchRunIdText(String(run.id))
            void handleRefetchExistingRun(stage, run.id)
          }}
          refetchingRunId={refetchStage?.runId ?? null}
          refetchingStage={refetchStage?.stage ?? null}
        />
      </div>
    </div>
  )
}