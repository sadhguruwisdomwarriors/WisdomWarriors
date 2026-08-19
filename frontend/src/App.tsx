import { useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { BrowserRouter, Routes, Route, NavLink, useLocation } from "react-router-dom"
import { LayoutDashboard, Users, FileText, CalendarClock, MessageSquare, Search, ShieldCheck, ChevronDown, ChevronRight, GitCompare, Swords, Grid3X3 } from "lucide-react"
import { clsx } from "clsx"
import DashboardPage from "./pages/Dashboard"
import ProfilesPage from "./pages/Profiles"
import { ProfileDetail } from "./pages/Profiles/ProfileDetail"
import { TaggedPostsPage } from "./pages/Profiles/TaggedPostsPage"
import PostsPage from "./pages/Posts"
import SchedulesPage from "./pages/Schedules"
import ChatPage from "./pages/Chat"
import ScrapePage from "./pages/Scrape"
import CompareRunsPage from "./pages/CompareRuns"
import WisdomWarriorsPage from "./pages/WisdomWarriors"
import MicroUnitsPage from "./pages/MicroUnits"
import PocDashboardView from "./pages/MicroUnits/PocDashboardView"
import { fetchWisdomWarriorsSnapshotRuns, type WisdomWarriorSnapshotRun } from "./api/wisdomWarriors"

const formatLocalDate = (value: string): string => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ""
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

const NAV = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard", end: true },
  { to: "/wisdom-warriors", icon: Swords, label: "Wisdom Warriors" },
  { to: "/micro-units", icon: Grid3X3, label: "Micro Units" },
  { to: "/profiles", icon: Users, label: "Profiles" },
  { to: "/posts", icon: FileText, label: "Posts" },
  { to: "/chat", icon: MessageSquare, label: "AI Chat" },
]

const ADMIN_NAV = [
  { to: "/scrape-instagram", icon: Search, label: "Wisdom Warriors Scraper" },
  { to: "/scrape-instagram/hashtag-scraper", icon: Search, label: "Hashtag Scraper" },
  { to: "/scrape-instagram/mentions-scraper", icon: Search, label: "Mentions Scraper" },
  { to: "/scrape-youtube", icon: Search, label: "YouTube Scraper" },
  { to: "/scrape-facebook", icon: Search, label: "Facebook Scraper" },
  { to: "/compare-runs", icon: GitCompare, label: "Compare Runs" },
  { to: "/schedules", icon: CalendarClock, label: "Schedules" },
]

function Sidebar() {
  const location = useLocation()
  const adminActive = ADMIN_NAV.some(item => location.pathname.startsWith(item.to))
  const [adminOpen, setAdminOpen] = useState(adminActive)

  return (
    <aside className="w-56 flex-shrink-0 border-r border-gray-800 flex flex-col py-6 px-3 gap-1">
      <div className="px-3 mb-6 flex items-center gap-2">
        <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="url(#ig-grad)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <defs>
            <linearGradient id="ig-grad" x1="2" y1="2" x2="22" y2="22">
              <stop offset="0%" stopColor="#f59e0b" />
              <stop offset="50%" stopColor="#ec4899" />
              <stop offset="100%" stopColor="#8b5cf6" />
            </linearGradient>
          </defs>
          <rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect>
          <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path>
          <line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line>
        </svg>
        <span className="text-lg font-bold text-white tracking-tight">Wisdom Warriors - Analytics</span>
      </div>
      {NAV.map(({ to, icon: Icon, label, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            clsx(
              "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
              isActive
                ? "bg-purple-800 text-white"
                : "text-gray-400 hover:text-white hover:bg-gray-800"
            )
          }
        >
          <Icon size={16} />
          {label}
        </NavLink>
      ))}

      {/* Admin group */}
      <div className="mt-1">
        <button
          onClick={() => setAdminOpen(o => !o)}
          className={clsx(
            "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
            adminActive
              ? "text-white"
              : "text-gray-400 hover:text-white hover:bg-gray-800"
          )}
        >
          <ShieldCheck size={16} />
          <span className="flex-1 text-left">Admin</span>
          {adminOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        {adminOpen && (
          <div className="ml-4 mt-0.5 flex flex-col gap-0.5 border-l border-gray-800 pl-2">
            <div className="px-3 py-1 text-[11px] uppercase tracking-wide text-gray-500">Instagram Scraper</div>
            {ADMIN_NAV.filter(item => item.to.startsWith("/scrape-instagram")).map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                    isActive
                      ? "bg-purple-800 text-white"
                      : "text-gray-400 hover:text-white hover:bg-gray-800"
                  )
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}

            <div className="px-3 py-1 text-[11px] uppercase tracking-wide text-gray-500">YouTube Scraper</div>
            {ADMIN_NAV.filter(item => item.to === "/scrape-youtube").map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                    isActive
                      ? "bg-purple-800 text-white"
                      : "text-gray-400 hover:text-white hover:bg-gray-800"
                  )
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}

            <div className="px-3 py-1 text-[11px] uppercase tracking-wide text-gray-500">Facebook Scraper</div>
            {ADMIN_NAV.filter(item => item.to === "/scrape-facebook").map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                    isActive
                      ? "bg-purple-800 text-white"
                      : "text-gray-400 hover:text-white hover:bg-gray-800"
                  )
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}

            <div className="px-3 py-1 text-[11px] uppercase tracking-wide text-gray-500">Admin Tools</div>
            {ADMIN_NAV.filter(item => !item.to.startsWith("/scrape-instagram") && item.to !== "/scrape-youtube" && item.to !== "/scrape-facebook").map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                    isActive
                      ? "bg-purple-800 text-white"
                      : "text-gray-400 hover:text-white hover:bg-gray-800"
                  )
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}

function AppContent() {
  const location = useLocation()
  const isMicroUnits = location.pathname.startsWith("/micro-units")

  const [selectedSnapshotRunId, setSelectedSnapshotRunId] = useState<number | undefined>(undefined)
  const [selectedMonth, setSelectedMonth] = useState("")
  const [selectedDateFrom, setSelectedDateFrom] = useState("")
  const [selectedDateTo, setSelectedDateTo] = useState("")

  const { data: snapshotRuns = [] } = useQuery({
    queryKey: ["global-snapshot-runs"],
    queryFn: () => fetchWisdomWarriorsSnapshotRuns(),
    refetchInterval: 30000,
  })

  const filteredSnapshotRuns = useMemo(() => {
    return snapshotRuns.filter(run => {
      const runDate = formatLocalDate(run.scraped_at)
      if (!runDate) return false
      if (selectedDateFrom && runDate < selectedDateFrom) return false
      if (selectedDateTo && runDate > selectedDateTo) return false
      return true
    })
  }, [snapshotRuns, selectedDateFrom, selectedDateTo])

  const hasInvalidDateRange = Boolean(selectedDateFrom && selectedDateTo && selectedDateFrom > selectedDateTo)

  useEffect(() => {
    if (hasInvalidDateRange) return
    if (filteredSnapshotRuns.length === 0) {
      setSelectedSnapshotRunId(undefined)
      return
    }
    if (selectedSnapshotRunId === undefined) {
      setSelectedSnapshotRunId(filteredSnapshotRuns[0].run_id)
      return
    }
    const selectedStillVisible = filteredSnapshotRuns.some(run => run.run_id === selectedSnapshotRunId)
    if (!selectedStillVisible) {
      setSelectedSnapshotRunId(filteredSnapshotRuns[0].run_id)
    }
  }, [filteredSnapshotRuns, hasInvalidDateRange, selectedSnapshotRunId])

  const selectedSnapshotRun = useMemo(
    () => filteredSnapshotRuns.find(run => run.run_id === selectedSnapshotRunId),
    [filteredSnapshotRuns, selectedSnapshotRunId]
  )

  useEffect(() => {
    if (!selectedSnapshotRun?.scraped_at) return
    const snapshotDate = formatLocalDate(selectedSnapshotRun.scraped_at)
    const snapshotMonth = snapshotDate.slice(0, 7)
    setSelectedMonth(snapshotMonth)
  }, [selectedSnapshotRun?.scraped_at])

  const selectedScrapedLabel = selectedSnapshotRun?.scraped_at
    ? new Date(selectedSnapshotRun.scraped_at).toLocaleString()
    : (hasInvalidDateRange ? "Invalid date range" : "No runs in selected range")

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100 overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto pr-4 md:pr-6 lg:pr-8">
        {!isMicroUnits && (
          <div className="sticky top-0 z-10 border-b border-gray-800 bg-gray-950/95 backdrop-blur px-4 py-2 text-xs text-gray-300">
            <div className="flex flex-wrap items-center gap-2">
              <label htmlFor="global-scraped-at" className="text-gray-300">Last scraped at:</label>
              <select
                id="global-scraped-at"
                value={selectedSnapshotRunId ?? ""}
                onChange={e => {
                  const value = e.target.value
                  setSelectedSnapshotRunId(value ? Number(value) : undefined)
                }}
                className="min-w-[240px] rounded border border-gray-700 bg-gray-900 px-2 py-1 text-xs text-gray-100"
                disabled={filteredSnapshotRuns.length === 0 || hasInvalidDateRange}
              >
                {filteredSnapshotRuns.length === 0 && <option value="">{selectedScrapedLabel}</option>}
                {filteredSnapshotRuns.map((run: WisdomWarriorSnapshotRun) => (
                  <option key={run.run_id} value={run.run_id}>
                    {new Date(run.scraped_at).toLocaleString()}
                  </option>
                ))}
              </select>

              <label htmlFor="global-month-filter" className="ml-1 text-gray-300">Month:</label>
              <input
                id="global-month-filter"
                type="month"
                value={selectedMonth}
                onChange={e => setSelectedMonth(e.target.value)}
                className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-xs text-gray-100"
              />

              <label htmlFor="global-date-from" className="ml-1 text-gray-300">From:</label>
              <input
                id="global-date-from"
                type="date"
                value={selectedDateFrom}
                onChange={e => setSelectedDateFrom(e.target.value)}
                className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-xs text-gray-100"
              />

              <label htmlFor="global-date-to" className="ml-1 text-gray-300">To:</label>
              <input
                id="global-date-to"
                type="date"
                value={selectedDateTo}
                min={selectedDateFrom || undefined}
                onChange={e => setSelectedDateTo(e.target.value)}
                className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-xs text-gray-100"
              />

              {hasInvalidDateRange && (
                <span className="text-[11px] text-red-400">From date must be on or before To date.</span>
              )}
            </div>
          </div>
        )}
        <div className={isMicroUnits ? "p-6" : ""}>
          <Routes>
            <Route
              path="/"
              element={
                <DashboardPage
                  selectedSnapshotRunId={selectedSnapshotRunId}
                  selectedScrapedAt={selectedSnapshotRun?.scraped_at}
                  selectedMonth={selectedMonth || undefined}
                />
              }
            />
            <Route
              path="/wisdom-warriors"
              element={<WisdomWarriorsPage selectedSnapshotRunId={selectedSnapshotRunId} selectedMonth={selectedMonth || undefined} />}
            />
            <Route path="/micro-units" element={<MicroUnitsPage />} />
            <Route path="/micro-units/:id" element={<PocDashboardView />} />
            <Route path="/scrape-instagram" element={<ScrapePage />} />
            <Route path="/scrape-instagram/hashtag-scraper" element={<ScrapePage />} />
            <Route path="/scrape-instagram/mentions-scraper" element={<ScrapePage />} />
            <Route path="/scrape-youtube" element={<ScrapePage />} />
            <Route path="/scrape-facebook" element={<ScrapePage />} />
            <Route path="/compare-runs" element={<CompareRunsPage />} />
            <Route path="/profiles" element={<ProfilesPage />} />
            <Route path="/profiles/:username" element={<ProfileDetail />} />
            <Route path="/profiles/:username/tagged-posts" element={<TaggedPostsPage />} />
            <Route path="/posts" element={<PostsPage selectedSnapshotRunId={selectedSnapshotRunId} />} />
            <Route path="/schedules" element={<SchedulesPage />} />
            <Route path="/chat" element={<ChatPage />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  )
}
