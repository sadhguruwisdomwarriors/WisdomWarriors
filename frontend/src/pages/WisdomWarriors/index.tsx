import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react"
import { FileSpreadsheet, Info, Pencil, Trash2, Upload, UserPlus } from "lucide-react"
import { clsx } from "clsx"
import {
  useWisdomWarriors,
  useWisdomWarriorsMonthlyViews,
  useCreateWisdomWarrior,
  useBulkCreateWisdomWarriors,
  useUpdateWisdomWarrior,
  useDeleteWisdomWarrior,
} from "../../hooks/useWisdomWarriors"
import { InfluencerModal } from "./InfluencerModal"
import { BulkInfluencerModal } from "./BulkInfluencerModal"
import { GoogleSheetSyncModal } from "./GoogleSheetSyncModal"
import type { WisdomWarrior, InfluencerCategory, InfluencerGrade, WisdomWarriorCreate } from "../../types/wisdomWarrior"

type Tab = "Dedicated" | "In-house influencer"

const FILTER_MENTIONS = [
  "ishafoundation",
  "adiyogi.official",
  "sadhguru",
  "sadhgurutamil",
  "sadhgurutelugu",
  "sadhguru.hindiofficial",
  "sadhguru.malayalam",
  "sadhguru_marathi_official",
  "sadhgurubangla",
  "sadhguru_kannada_official",
]

const FILTER_TAGGED_USERS = [
  "ishafoundation",
  "adiyogi.official",
  "sadhguru",
  "sadhgurutamil",
  "sadhgurutelugu",
  "sadhguru.hindiofficial",
  "sadhguru.malayalam",
  "sadhguru_marathi_official",
  "sadhgurubangla",
  "sadhguru_kannada_official",
]

const FILTER_HASHTAGS = [
  "Isha",
  "Ishafoundation",
  "Ishayogacenter",
  "Sadhguru",
  "Sadhgurujaggivasudev",
  "Jaggi",
  "Adiyogi",
  "Linga Bhairavi",
  "Adiyogishiva",
  "ஈஷா",
]

const FILTER_CAPTION_KEYWORDS = [
  "Isha",
  "Ishafoundation",
  "Ishayogacenter",
  "Sadhguru",
  "Sadhgurujaggivasudev",
  "Jaggi",
  "Adiyogi",
  "Linga Bhairavi",
  "Adiyogishiva",
  "ஈஷா",
  "ईशा",
  "ఇషా",
  "ഇഷ",
  "ಇಶಾ",
  "சத்குரு",
  "సద్గురు",
  "ಸದ್ಗುರು",
  "സദ്‍ഗുരു",
  "सद्गुरु",
]

const WISDOM_WARRIORS_FILTERS_STORAGE_KEY = "insta-analytics.wisdom-warriors.in-house-filters"

function getStoredWisdomFilterList(key: "hashtags" | "mentions" | "taggedUsers" | "keywords", fallback: string[]) {
  if (typeof window === "undefined") return fallback

  try {
    const raw = window.localStorage.getItem(WISDOM_WARRIORS_FILTERS_STORAGE_KEY)
    if (!raw) return fallback

    const parsed = JSON.parse(raw) as Partial<Record<"hashtags" | "mentions" | "taggedUsers" | "keywords", string[]>>
    const values = parsed[key]
    if (!Array.isArray(values)) return fallback

    const cleaned = values
      .filter((value): value is string => typeof value === "string")
      .map(value => value.trim())
      .filter(Boolean)

    return Array.from(new Set(cleaned))
  } catch {
    return fallback
  }
}

const GRADE_COLORS: Record<string, string> = {
  A: "bg-emerald-900/60 text-emerald-300 border-emerald-700",
  B: "bg-blue-900/60 text-blue-300 border-blue-700",
  C: "bg-yellow-900/60 text-yellow-300 border-yellow-700",
  D: "bg-orange-900/60 text-orange-300 border-orange-700",
  E: "bg-red-900/60 text-red-300 border-red-700",
  Inactive: "bg-gray-800 text-gray-400 border-gray-600",
}

const GRADE_ORDER: InfluencerGrade[] = ["A", "B", "C", "D", "E", "Inactive"]

function GradeBadge({ grade }: { grade: string | null }) {
  if (!grade) return <span className="text-gray-600 text-xs">—</span>
  return (
    <span
      className={clsx(
        "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border",
        GRADE_COLORS[grade] ?? "bg-gray-800 text-gray-400 border-gray-600"
      )}
    >
      {grade}
    </span>
  )
}

function MatchList({ values }: { values: string[] | undefined }) {
  if (!values || values.length === 0) return <span className="text-gray-600 text-xs">—</span>
  return (
    <div className="flex flex-wrap gap-1">
      {values.map(value => (
        <span
          key={value}
          className="inline-flex items-center rounded-full border border-gray-700 bg-gray-900 px-2 py-0.5 text-[11px] text-gray-300"
        >
          {value}
        </span>
      ))}
    </div>
  )
}

function formatViewCount(value: number) {
  return Math.round(value).toLocaleString()
}

interface WisdomWarriorsPageProps {
  selectedSnapshotRunId?: number
  selectedMonth?: string
}

export default function WisdomWarriorsPage({ selectedSnapshotRunId, selectedMonth }: WisdomWarriorsPageProps) {
  const [activeTab, setActiveTab] = useState<Tab>("Dedicated")
  const [draftHashtags, setDraftHashtags] = useState<string[]>(() => getStoredWisdomFilterList("hashtags", FILTER_HASHTAGS))
  const [draftMentions, setDraftMentions] = useState<string[]>(() => getStoredWisdomFilterList("mentions", FILTER_MENTIONS))
  const [draftTaggedUsers, setDraftTaggedUsers] = useState<string[]>(() => getStoredWisdomFilterList("taggedUsers", FILTER_TAGGED_USERS))
  const [draftKeywords, setDraftKeywords] = useState<string[]>(() => getStoredWisdomFilterList("keywords", FILTER_CAPTION_KEYWORDS))
  const [appliedHashtags, setAppliedHashtags] = useState<string[]>(() => getStoredWisdomFilterList("hashtags", FILTER_HASHTAGS))
  const [appliedMentions, setAppliedMentions] = useState<string[]>(() => getStoredWisdomFilterList("mentions", FILTER_MENTIONS))
  const [appliedTaggedUsers, setAppliedTaggedUsers] = useState<string[]>(() => getStoredWisdomFilterList("taggedUsers", FILTER_TAGGED_USERS))
  const [appliedKeywords, setAppliedKeywords] = useState<string[]>(() => getStoredWisdomFilterList("keywords", FILTER_CAPTION_KEYWORDS))
  const [newHashtag, setNewHashtag] = useState("")
  const [newMention, setNewMention] = useState("")
  const [newTaggedUser, setNewTaggedUser] = useState("")
  const [newKeyword, setNewKeyword] = useState("")
  const [showModal, setShowModal] = useState(false)
  const [showBulkModal, setShowBulkModal] = useState(false)
  const [showSheetSyncModal, setShowSheetSyncModal] = useState(false)
  const [editing, setEditing] = useState<WisdomWarrior | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null)
  const [bulkMessage, setBulkMessage] = useState("")
  const effectiveMonth = selectedMonth || new Date().toISOString().slice(0, 7)

  const { data: all = [], isLoading } = useWisdomWarriors()
  const isInHouse = activeTab === "In-house influencer"
  const dedicatedMonthlyViewsQuery = useWisdomWarriorsMonthlyViews({
    month: effectiveMonth,
    applyFilters: false,
    snapshotRunId: selectedSnapshotRunId,
    category: "Dedicated",
  })
  const inHouseMonthlyViewsQuery = useWisdomWarriorsMonthlyViews({
    month: effectiveMonth,
    applyFilters: true,
    snapshotRunId: selectedSnapshotRunId,
    category: "In-house influencer",
    hashtags: appliedHashtags,
    mentions: appliedMentions,
    taggedUsers: appliedTaggedUsers,
    keywords: appliedKeywords,
  })
  const dedicatedMonthlyViews = dedicatedMonthlyViewsQuery.data ?? []
  const inHouseMonthlyViews = inHouseMonthlyViewsQuery.data ?? []
  const monthlyViews = isInHouse ? inHouseMonthlyViews : dedicatedMonthlyViews
  const isSnapshotSelectionPending = selectedSnapshotRunId === undefined
  const isMonthlyViewsLoading = isSnapshotSelectionPending || (isInHouse ? inHouseMonthlyViewsQuery.isLoading : dedicatedMonthlyViewsQuery.isLoading)
  const isCombinedTotalsLoading = isSnapshotSelectionPending || dedicatedMonthlyViewsQuery.isLoading || inHouseMonthlyViewsQuery.isLoading
  const create = useCreateWisdomWarrior()
  const bulkCreate = useBulkCreateWisdomWarriors()
  const update = useUpdateWisdomWarrior()
  const remove = useDeleteWisdomWarrior()

  const monthlyViewsByUsername = useMemo(
    () => new Map(monthlyViews.map(item => [item.username.toLowerCase(), item])),
    [monthlyViews]
  )

  const rows = useMemo(() => all.filter(w => w.category === activeTab), [all, activeTab])
  const dedicatedTotalViews = useMemo(
    () => dedicatedMonthlyViews.reduce((sum, item) => sum + item.total_views, 0),
    [dedicatedMonthlyViews]
  )
  const inHouseTotalViews = useMemo(
    () => inHouseMonthlyViews.reduce((sum, item) => sum + item.total_views, 0),
    [inHouseMonthlyViews]
  )
  const combinedMonthlyTotalViews = dedicatedTotalViews + inHouseTotalViews
  const gradeSummaries = useMemo(() => {
    return GRADE_ORDER.map(grade => {
      const influencers = rows.filter(warrior => warrior.grade === grade)
      const totalViews = influencers.reduce(
        (sum, warrior) => sum + (monthlyViewsByUsername.get(warrior.username.toLowerCase())?.total_views ?? 0),
        0
      )
      return { grade, count: influencers.length, totalViews }
    })
  }, [monthlyViewsByUsername, rows])
  const currentCategoryTotalViews = useMemo(
    () => gradeSummaries.reduce((sum, summary) => sum + summary.totalViews, 0),
    [gradeSummaries]
  )

  useEffect(() => {
    window.localStorage.setItem(
      WISDOM_WARRIORS_FILTERS_STORAGE_KEY,
      JSON.stringify({
        hashtags: draftHashtags,
        mentions: draftMentions,
        taggedUsers: draftTaggedUsers,
        keywords: draftKeywords,
      })
    )
  }, [draftHashtags, draftMentions, draftTaggedUsers, draftKeywords])

  function handleCreate(data: WisdomWarriorCreate) {
    // Force the category to match the active tab when adding from that tab
    const payload = { ...data, category: (data.category ?? activeTab) as InfluencerCategory }
    create.mutate(payload, {
      onSuccess: () => {
        setBulkMessage("")
        setShowModal(false)
      },
    })
  }

  function handleBulkCreate(items: WisdomWarriorCreate[]) {
    bulkCreate.mutate(items, {
      onSuccess: result => {
        const messageParts: string[] = []
        if (result.created.length > 0) messageParts.push(`Added ${result.created.length} influencer(s)`)
        if (result.skipped_existing.length > 0) messageParts.push(`Skipped ${result.skipped_existing.length} existing`)
        setBulkMessage(messageParts.join(" • ") || "No new influencers were added.")
        setShowBulkModal(false)
      },
    })
  }

  function handleEdit(data: WisdomWarriorCreate) {
    if (!editing) return
    update.mutate(
      { id: editing.id, body: data },
      { onSuccess: () => setEditing(null) }
    )
  }

  function handleDelete(id: number) {
    remove.mutate(id, { onSuccess: () => setDeleteConfirm(null) })
  }

  function addFilterValue(value: string, setter: Dispatch<SetStateAction<string[]>>) {
    const normalized = value.trim()
    if (!normalized) return
    setter(prev => (prev.some(v => v.toLowerCase() === normalized.toLowerCase()) ? prev : [...prev, normalized]))
  }

  function removeFilterValue(value: string, setter: Dispatch<SetStateAction<string[]>>) {
    setter(prev => prev.filter(v => v !== value))
  }

  function applyFilters() {
    setAppliedHashtags(draftHashtags)
    setAppliedMentions(draftMentions)
    setAppliedTaggedUsers(draftTaggedUsers)
    setAppliedKeywords(draftKeywords)
  }

  const tabs: Tab[] = ["Dedicated", "In-house influencer"]

  return (
    <div className="space-y-4 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Wisdom Warriors</h1>
          <p className="text-sm text-gray-400 mt-0.5">Manage influencer profiles tracked by the scraper</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowSheetSyncModal(true)}
            className="flex items-center gap-2 rounded-lg bg-emerald-700 px-3 py-1.5 text-sm text-white transition-colors hover:bg-emerald-600 shadow-md shadow-emerald-950/40"
          >
            <FileSpreadsheet size={15} />
            Sync Google Sheet
          </button>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 rounded-lg bg-purple-700 px-3 py-1.5 text-sm text-white transition-colors hover:bg-purple-600"
          >
            <UserPlus size={15} />
            Add Influencer
          </button>
          <button
            onClick={() => setShowBulkModal(true)}
            className="flex items-center gap-2 rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-gray-200 transition-colors hover:bg-gray-800"
          >
            <Upload size={15} />
            Bulk Add
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-purple-800/60 bg-purple-950/30 p-4">
        <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-purple-300">Total views for {effectiveMonth}</p>
        <div className="mt-3 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-3xl font-semibold text-white">
              {isCombinedTotalsLoading ? "..." : formatViewCount(combinedMonthlyTotalViews)}
            </p>
            <p className="mt-1 text-xs text-gray-400">
              Combined cumulative views from Dedicated and In-house influencers after all calculations and filters.
            </p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="rounded-lg border border-gray-800 bg-gray-950/70 px-3 py-2">
              <p className="text-[11px] text-gray-400">Dedicated</p>
              <p className="text-sm font-semibold text-white">
                {dedicatedMonthlyViewsQuery.isLoading ? "..." : formatViewCount(dedicatedTotalViews)}
              </p>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-950/70 px-3 py-2">
              <p className="text-[11px] text-gray-400">In-house influencer</p>
              <p className="text-sm font-semibold text-white">
                {inHouseMonthlyViewsQuery.isLoading ? "..." : formatViewCount(inHouseTotalViews)}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800">
        {tabs.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={clsx(
              "px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px",
              activeTab === tab
                ? "border-purple-500 text-purple-300"
                : "border-transparent text-gray-400 hover:text-gray-200"
            )}
          >
            {tab}
            <span className={clsx(
              "ml-2 text-xs px-1.5 py-0.5 rounded-full",
              activeTab === tab ? "bg-purple-800 text-purple-200" : "bg-gray-800 text-gray-500"
            )}>
              {all.filter(w => w.category === tab).length}
            </span>
          </button>
        ))}
      </div>

      {bulkMessage && (
        <div className="rounded-lg border border-emerald-800 bg-emerald-950/40 px-3 py-2 text-sm text-emerald-200">
          {bulkMessage}
        </div>
      )}

      <div className="rounded-xl border border-gray-800 bg-gray-900/70 p-4">
        <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-gray-400">{activeTab} total views for {effectiveMonth}</p>
        <p className="mt-2 text-2xl font-semibold text-white">
          {isMonthlyViewsLoading ? "..." : formatViewCount(currentCategoryTotalViews)}
        </p>
        <p className="mt-1 text-xs text-gray-400">
          Cumulative of all grade categories after the current calculations{isInHouse ? " and applied filters" : ""}.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        {gradeSummaries.map(summary => (
          <div key={summary.grade} className="rounded-xl border border-gray-800 bg-gray-900/70 p-3">
            <div className="flex items-center justify-between gap-2">
              <GradeBadge grade={summary.grade} />
              <span className="text-[11px] text-gray-500">{summary.count} influencer(s)</span>
            </div>
            <div className="mt-3 text-xl font-semibold text-white">
              {isMonthlyViewsLoading ? "..." : formatViewCount(summary.totalViews)}
            </div>
            <p className="mt-1 text-[11px] text-gray-400">Total views for {summary.grade}</p>
          </div>
        ))}
      </div>

      {isInHouse && (
        <div className="rounded-xl border border-gray-800 bg-gray-900/70 p-4 space-y-4">
          <div>
            <h2 className="text-sm font-semibold text-gray-200">View Count Filters</h2>
            <p className="text-xs text-gray-400 mt-1">
              In-house monthly views only include posts from {effectiveMonth} that match at least one allowed hashtag, mention, tagged user, or caption keyword.
            </p>
          </div>
          <div className="grid gap-3 lg:grid-cols-4">
            <div>
              <p className="text-xs font-medium text-gray-400 mb-2">Allowed Hashtags</p>
              <div className="flex gap-2 mb-2">
                <input
                  value={newHashtag}
                  onChange={e => setNewHashtag(e.target.value)}
                  placeholder="Add hashtag"
                  className="w-full rounded-lg border border-gray-700 bg-gray-900 px-2 py-1.5 text-xs text-gray-200"
                />
                <button
                  type="button"
                  onClick={() => {
                    addFilterValue(newHashtag, setDraftHashtags)
                    setNewHashtag("")
                  }}
                  className="rounded-lg border border-gray-700 px-2 py-1 text-xs text-gray-200 hover:bg-gray-800"
                >
                  Add
                </button>
              </div>
              <div className="flex flex-wrap gap-1">
                {draftHashtags.map(value => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => removeFilterValue(value, setDraftHashtags)}
                    className="inline-flex items-center rounded-full border border-gray-700 bg-gray-900 px-2 py-0.5 text-[11px] text-gray-300 hover:border-red-700 hover:text-red-300"
                    title="Remove"
                  >
                    {value} ×
                  </button>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-400 mb-2">Allowed Mentions</p>
              <div className="flex gap-2 mb-2">
                <input
                  value={newMention}
                  onChange={e => setNewMention(e.target.value)}
                  placeholder="Add mention"
                  className="w-full rounded-lg border border-gray-700 bg-gray-900 px-2 py-1.5 text-xs text-gray-200"
                />
                <button
                  type="button"
                  onClick={() => {
                    addFilterValue(newMention, setDraftMentions)
                    setNewMention("")
                  }}
                  className="rounded-lg border border-gray-700 px-2 py-1 text-xs text-gray-200 hover:bg-gray-800"
                >
                  Add
                </button>
              </div>
              <div className="flex flex-wrap gap-1">
                {draftMentions.map(value => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => removeFilterValue(value, setDraftMentions)}
                    className="inline-flex items-center rounded-full border border-gray-700 bg-gray-900 px-2 py-0.5 text-[11px] text-gray-300 hover:border-red-700 hover:text-red-300"
                    title="Remove"
                  >
                    {value} ×
                  </button>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-400 mb-2">Allowed Caption Keywords</p>
              <div className="flex gap-2 mb-2">
                <input
                  value={newKeyword}
                  onChange={e => setNewKeyword(e.target.value)}
                  placeholder="Add keyword"
                  className="w-full rounded-lg border border-gray-700 bg-gray-900 px-2 py-1.5 text-xs text-gray-200"
                />
                <button
                  type="button"
                  onClick={() => {
                    addFilterValue(newKeyword, setDraftKeywords)
                    setNewKeyword("")
                  }}
                  className="rounded-lg border border-gray-700 px-2 py-1 text-xs text-gray-200 hover:bg-gray-800"
                >
                  Add
                </button>
              </div>
              <div className="flex flex-wrap gap-1">
                {draftKeywords.map(value => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => removeFilterValue(value, setDraftKeywords)}
                    className="inline-flex items-center rounded-full border border-gray-700 bg-gray-900 px-2 py-0.5 text-[11px] text-gray-300 hover:border-red-700 hover:text-red-300"
                    title="Remove"
                  >
                    {value} ×
                  </button>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-400 mb-2">Allowed Tagged Users</p>
              <div className="flex gap-2 mb-2">
                <input
                  value={newTaggedUser}
                  onChange={e => setNewTaggedUser(e.target.value)}
                  placeholder="Add tagged user"
                  className="w-full rounded-lg border border-gray-700 bg-gray-900 px-2 py-1.5 text-xs text-gray-200"
                />
                <button
                  type="button"
                  onClick={() => {
                    addFilterValue(newTaggedUser, setDraftTaggedUsers)
                    setNewTaggedUser("")
                  }}
                  className="rounded-lg border border-gray-700 px-2 py-1 text-xs text-gray-200 hover:bg-gray-800"
                >
                  Add
                </button>
              </div>
              <div className="flex flex-wrap gap-1">
                {draftTaggedUsers.map(value => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => removeFilterValue(value, setDraftTaggedUsers)}
                    className="inline-flex items-center rounded-full border border-gray-700 bg-gray-900 px-2 py-0.5 text-[11px] text-gray-300 hover:border-red-700 hover:text-red-300"
                    title="Remove"
                  >
                    {value} ×
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={applyFilters}
              className="rounded-lg bg-purple-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-600"
            >
              Apply
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-900 text-gray-400 text-xs uppercase tracking-wide">
              <th className="px-4 py-3 text-left font-medium">#</th>
              <th className="px-4 py-3 text-left font-medium">Username</th>
              <th className="px-4 py-3 text-left font-medium">Grade</th>
              <th className="px-4 py-3 text-left font-medium">
                <div className="flex items-center gap-1">
                  <span>Monthly Views ({effectiveMonth})</span>
                  <div className="relative group">
                    <Info className="w-3.5 h-3.5 text-gray-500 cursor-help" />
                    <div className="absolute left-1/2 -translate-x-1/2 top-5 z-10 hidden group-hover:block w-72 rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-xs text-gray-300 shadow-lg normal-case tracking-normal font-normal">
                      {isInHouse
                        ? "Views are collaborator-adjusted: each post's views are divided by the total number of creators (owner + collaborators). Only posts matching the applied hashtag, mention, tagged-user, or caption keyword filters are counted."
                        : "Views are collaborator-adjusted: each post's views are divided by the total number of creators (owner + collaborators)."}
                    </div>
                  </div>
                </div>
              </th>
              <th className="px-4 py-3 text-left font-medium">Hashtags</th>
              <th className="px-4 py-3 text-left font-medium">Mentions</th>
              <th className="px-4 py-3 text-left font-medium">Tagged Users</th>
              <th className="px-4 py-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {isLoading && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-500 text-sm">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && rows.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-500 text-sm">
                  No {activeTab} influencers yet. Click <span className="text-purple-400">Add Influencer</span> to get started.
                </td>
              </tr>
            )}
            {rows.map((warrior, idx) => (
              <tr key={warrior.id} className="bg-gray-950 hover:bg-gray-900 transition-colors">
                <td className="px-4 py-3 text-gray-500">{idx + 1}</td>
                <td className="px-4 py-3 font-medium text-gray-100">
                  <a
                    href={`https://www.instagram.com/${warrior.username}/`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2.5 hover:text-purple-400 transition-colors group"
                  >
                    {warrior.profile_pic_url ? (
                      <img
                        src={warrior.profile_pic_url}
                        alt={warrior.username}
                        className="w-8 h-8 rounded-full object-cover flex-shrink-0 ring-1 ring-gray-700"
                        onError={(e) => {
                          const target = e.currentTarget
                          target.style.display = "none"
                          const next = target.nextElementSibling as HTMLElement | null
                          if (next) next.style.display = "flex"
                        }}
                      />
                    ) : null}
                    <span
                      className="w-8 h-8 rounded-full bg-gray-800 ring-1 ring-gray-700 flex-shrink-0 items-center justify-center text-xs font-semibold text-gray-400 uppercase"
                      style={{ display: warrior.profile_pic_url ? "none" : "flex" }}
                    >
                      {warrior.username.charAt(0)}
                    </span>
                    <span>@{warrior.username}</span>
                  </a>
                </td>
                <td className="px-4 py-3">
                  <GradeBadge grade={warrior.grade} />
                </td>
                <td className="px-4 py-3 text-gray-200 align-top">
                  {isMonthlyViewsLoading
                    ? "..."
                    : formatViewCount(monthlyViewsByUsername.get(warrior.username.toLowerCase())?.total_views ?? 0)}
                </td>
                <td className="px-4 py-3 align-top">
                  <MatchList values={monthlyViewsByUsername.get(warrior.username.toLowerCase())?.matched_hashtags} />
                </td>
                <td className="px-4 py-3 align-top">
                  <MatchList values={monthlyViewsByUsername.get(warrior.username.toLowerCase())?.matched_mentions} />
                </td>
                <td className="px-4 py-3 align-top">
                  <MatchList values={monthlyViewsByUsername.get(warrior.username.toLowerCase())?.matched_tagged_users} />
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={() => setEditing(warrior)}
                      className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
                      title="Edit"
                    >
                      <Pencil size={14} />
                    </button>
                    {deleteConfirm === warrior.id ? (
                      <span className="flex items-center gap-1">
                        <button
                          onClick={() => handleDelete(warrior.id)}
                          className="px-2 py-1 text-xs bg-red-700 hover:bg-red-600 text-white rounded transition-colors"
                        >
                          Confirm
                        </button>
                        <button
                          onClick={() => setDeleteConfirm(null)}
                          className="px-2 py-1 text-xs text-gray-400 hover:text-gray-200 transition-colors"
                        >
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <button
                        onClick={() => setDeleteConfirm(warrior.id)}
                        className="p-1.5 rounded-lg text-gray-400 hover:text-red-400 hover:bg-gray-800 transition-colors"
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Unassigned notice */}
      {all.some(w => !w.category) && (
        <p className="text-xs text-gray-500">
          {all.filter(w => !w.category).length} influencer(s) have no category assigned and are not shown in any tab.
        </p>
      )}

      {/* Modals */}
      {showModal && (
        <InfluencerModal
          onSubmit={handleCreate}
          onClose={() => setShowModal(false)}
          initialData={{ id: 0, username: "", category: activeTab, grade: null, position: 0 }}
        />
      )}
      {showBulkModal && (
        <BulkInfluencerModal
          initialCategory={activeTab}
          isSubmitting={bulkCreate.isPending}
          onSubmit={handleBulkCreate}
          onClose={() => setShowBulkModal(false)}
        />
      )}
      {editing && (
        <InfluencerModal
          onSubmit={handleEdit}
          onClose={() => setEditing(null)}
          initialData={editing}
        />
      )}
      <GoogleSheetSyncModal
        isOpen={showSheetSyncModal}
        onClose={() => setShowSheetSyncModal(false)}
      />
    </div>
  )
}
