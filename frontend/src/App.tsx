import { useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { BrowserRouter, Routes, Route, NavLink, useLocation, Navigate } from "react-router-dom"
import { LayoutDashboard, Users, FileText, CalendarClock, MessageSquare, Search, ShieldCheck, ChevronDown, ChevronRight, GitCompare, Swords, Grid3X3, LogOut, User as UserIcon } from "lucide-react"
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
import LoginPage from "./pages/Login"
import { getMe, logout, getToken, type User } from "./api/auth"
import { fetchWisdomWarriorsSnapshotRuns, type WisdomWarriorSnapshotRun } from "./api/wisdomWarriors"

const formatLocalDate = (value: string): string => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ""
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

interface NavItem {
  to: string;
  icon: any;
  label: string;
  end?: boolean;
}

const ADMIN_MAIN_NAV: NavItem[] = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard", end: true },
  { to: "/wisdom-warriors", icon: Swords, label: "Wisdom Warriors" },
  { to: "/micro-units", icon: Grid3X3, label: "Micro Units" },
  { to: "/profiles", icon: Users, label: "Profiles" },
  { to: "/posts", icon: FileText, label: "Posts" },
  { to: "/chat", icon: MessageSquare, label: "AI Chat" },
]

const POC_MAIN_NAV: NavItem[] = [
  { to: "/micro-units", icon: Grid3X3, label: "Micro Units" },
]

const ADMIN_SCRAPER_NAV = [
  { to: "/scrape-instagram", icon: Search, label: "Wisdom Warriors Scraper" },
  { to: "/scrape-instagram/hashtag-scraper", icon: Search, label: "Hashtag Scraper" },
  { to: "/scrape-instagram/mentions-scraper", icon: Search, label: "Mentions Scraper" },
  { to: "/scrape-youtube", icon: Search, label: "YouTube Scraper" },
  { to: "/scrape-facebook", icon: Search, label: "Facebook Scraper" },
  { to: "/compare-runs", icon: GitCompare, label: "Compare Runs" },
  { to: "/schedules", icon: CalendarClock, label: "Schedules" },
]

function Sidebar({ currentUser, onLogout }: { currentUser: User; onLogout: () => void }) {
  const location = useLocation()
  const isAdmin = currentUser.role === "ADMIN"
  const adminActive = ADMIN_SCRAPER_NAV.some(item => location.pathname.startsWith(item.to))
  const [adminOpen, setAdminOpen] = useState(adminActive)

  const navItems = isAdmin ? ADMIN_MAIN_NAV : POC_MAIN_NAV

  return (
    <aside className="w-60 flex-shrink-0 border-r border-gray-800 flex flex-col justify-between py-6 px-3 bg-gray-950">
      <div className="flex flex-col gap-1">
        <div className="px-3 mb-6 flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-yellow-400 via-pink-500 to-purple-600 p-0.5 shadow-md shadow-purple-500/20 flex items-center justify-center flex-shrink-0">
            <div className="w-full h-full bg-gray-950 rounded-[6px] flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect>
                <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path>
                <line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line>
              </svg>
            </div>
          </div>
          <span className="text-sm font-bold text-white tracking-tight leading-tight">Wisdom Warriors<br /><span className="text-gray-400 font-normal text-xs">Analytics</span></span>
        </div>

        {navItems.map(({ to, icon: Icon, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                isActive
                  ? "bg-purple-800 text-white font-medium shadow-sm shadow-purple-900/50"
                  : "text-gray-400 hover:text-white hover:bg-gray-900"
              )
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}

        {/* Admin Scrapers group - only for ADMIN */}
        {isAdmin && (
          <div className="mt-2">
            <button
              onClick={() => setAdminOpen(o => !o)}
              className={clsx(
                "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                adminActive
                  ? "text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-900"
              )}
            >
              <ShieldCheck size={16} />
              <span className="flex-1 text-left text-xs font-semibold uppercase tracking-wider text-gray-400">Admin Tools</span>
              {adminOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>
            {adminOpen && (
              <div className="ml-4 mt-1 flex flex-col gap-0.5 border-l border-gray-800 pl-2">
                <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-gray-500 font-semibold">Instagram Scraper</div>
                {ADMIN_SCRAPER_NAV.filter(item => item.to.startsWith("/scrape-instagram")).map(({ to, icon: Icon, label }) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                      clsx(
                        "flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs transition-colors",
                        isActive
                          ? "bg-purple-800 text-white font-medium"
                          : "text-gray-400 hover:text-white hover:bg-gray-900"
                      )
                    }
                  >
                    <Icon size={14} />
                    {label}
                  </NavLink>
                ))}

                <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-gray-500 font-semibold mt-1">YouTube Scraper</div>
                {ADMIN_SCRAPER_NAV.filter(item => item.to === "/scrape-youtube").map(({ to, icon: Icon, label }) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                      clsx(
                        "flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs transition-colors",
                        isActive
                          ? "bg-purple-800 text-white font-medium"
                          : "text-gray-400 hover:text-white hover:bg-gray-900"
                      )
                    }
                  >
                    <Icon size={14} />
                    {label}
                  </NavLink>
                ))}

                <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-gray-500 font-semibold mt-1">Facebook Scraper</div>
                {ADMIN_SCRAPER_NAV.filter(item => item.to === "/scrape-facebook").map(({ to, icon: Icon, label }) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                      clsx(
                        "flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs transition-colors",
                        isActive
                          ? "bg-purple-800 text-white font-medium"
                          : "text-gray-400 hover:text-white hover:bg-gray-900"
                      )
                    }
                  >
                    <Icon size={14} />
                    {label}
                  </NavLink>
                ))}

                <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-gray-500 font-semibold mt-1">Schedules & Compare</div>
                {ADMIN_SCRAPER_NAV.filter(item => !item.to.startsWith("/scrape-instagram") && item.to !== "/scrape-youtube" && item.to !== "/scrape-facebook").map(({ to, icon: Icon, label }) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                      clsx(
                        "flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs transition-colors",
                        isActive
                          ? "bg-purple-800 text-white font-medium"
                          : "text-gray-400 hover:text-white hover:bg-gray-900"
                      )
                    }
                  >
                    <Icon size={14} />
                    {label}
                  </NavLink>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* User profile footer */}
      <div className="pt-4 border-t border-gray-800 flex items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-2 overflow-hidden">
          <div className="w-8 h-8 rounded-full bg-gray-800 border border-gray-700 flex items-center justify-center flex-shrink-0 text-purple-400">
            <UserIcon size={16} />
          </div>
          <div className="overflow-hidden">
            <div className="text-xs font-semibold text-white truncate">{currentUser.full_name}</div>
            <div className="flex items-center gap-1.5">
              <span className={clsx(
                "text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.2 rounded border",
                isAdmin 
                  ? "bg-purple-950/80 text-purple-300 border-purple-800" 
                  : "bg-emerald-950/80 text-emerald-300 border-emerald-800"
              )}>
                {currentUser.role}
              </span>
            </div>
          </div>
        </div>
        <button
          onClick={onLogout}
          title="Log Out"
          className="p-1.5 text-gray-400 hover:text-red-400 hover:bg-gray-900 rounded-lg transition-colors"
        >
          <LogOut size={16} />
        </button>
      </div>
    </aside>
  )
}

function AppContent({ currentUser, onLogout }: { currentUser: User; onLogout: () => void }) {
  const location = useLocation()
  const isAdmin = currentUser.role === "ADMIN"
  const isMicroUnits = location.pathname.startsWith("/micro-units")

  const [selectedSnapshotRunId, setSelectedSnapshotRunId] = useState<number | undefined>(undefined)
  const [selectedMonth, setSelectedMonth] = useState("")
  const [selectedDateFrom, setSelectedDateFrom] = useState("")
  const [selectedDateTo, setSelectedDateTo] = useState("")

  const { data: snapshotRuns = [] } = useQuery({
    queryKey: ["global-snapshot-runs"],
    queryFn: () => fetchWisdomWarriorsSnapshotRuns(),
    refetchInterval: 30000,
    enabled: isAdmin,
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

  // If user is POC, enforce micro-units only
  if (!isAdmin) {
    return (
      <div className="flex h-screen bg-gray-950 text-gray-100 overflow-hidden">
        <Sidebar currentUser={currentUser} onLogout={onLogout} />
        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route path="/micro-units" element={<MicroUnitsPage currentUser={currentUser} />} />
            <Route path="/micro-units/:id" element={<PocDashboardView />} />
            <Route path="*" element={<Navigate to="/micro-units" replace />} />
          </Routes>
        </main>
      </div>
    )
  }

  // If user is ADMIN, full access
  return (
    <div className="flex h-screen bg-gray-950 text-gray-100 overflow-hidden">
      <Sidebar currentUser={currentUser} onLogout={onLogout} />
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
            <Route path="/micro-units" element={<MicroUnitsPage currentUser={currentUser} />} />
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
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  const [authChecked, setAuthChecked] = useState(false)

  const checkAuth = async () => {
    const token = getToken()
    if (token) {
      try {
        const user = await getMe()
        setCurrentUser(user)
      } catch {
        logout()
        setCurrentUser(null)
      }
    } else {
      setCurrentUser(null)
    }
    setAuthChecked(true)
  }

  useEffect(() => {
    checkAuth()
  }, [])

  const handleLogout = () => {
    logout()
    setCurrentUser(null)
  }

  if (!authChecked) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center text-gray-400 text-sm">
        <div className="flex items-center gap-3">
          <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
          <span>Loading Wisdom Warriors...</span>
        </div>
      </div>
    )
  }

  if (!currentUser) {
    return <LoginPage onLoginSuccess={(user) => setCurrentUser(user)} />
  }

  return (
    <BrowserRouter>
      <AppContent currentUser={currentUser} onLogout={handleLogout} />
    </BrowserRouter>
  )
}
