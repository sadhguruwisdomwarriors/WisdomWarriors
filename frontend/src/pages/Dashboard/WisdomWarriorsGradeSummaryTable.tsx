import { useMemo } from "react"
import { ChartCard } from "../../components/ChartCard"
import { useWisdomWarriors, useWisdomWarriorsMonthlyViews } from "../../hooks/useWisdomWarriors"
import type { InfluencerGrade } from "../../types/wisdomWarrior"

interface WisdomWarriorsGradeSummaryTableProps {
  selectedSnapshotRunId?: number
  monthLabel?: string
}

type GradeSummary = {
  grade: InfluencerGrade
  dedicatedCount: number
  inHouseCount: number
  dedicatedTotalViews: number
  inHouseTotalViews: number
  dedicatedTopChannels: { username: string; views: number }[]
  inHouseTopChannels: { username: string; views: number }[]
}

const GRADE_ORDER: InfluencerGrade[] = ["A", "B", "C", "D", "E", "Inactive"]
const WISDOM_WARRIORS_FILTERS_STORAGE_KEY = "insta-analytics.wisdom-warriors.in-house-filters"
const GRADE_BADGE_STYLES: Record<InfluencerGrade, string> = {
  A: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
  B: "border-cyan-500/40 bg-cyan-500/10 text-cyan-200",
  C: "border-sky-500/40 bg-sky-500/10 text-sky-200",
  D: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  E: "border-rose-500/40 bg-rose-500/10 text-rose-200",
  Inactive: "border-gray-500/40 bg-gray-500/10 text-gray-200",
}

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
  "Sadhguru",
  "Sadhgurujaggivasudev",
  "Sadguru",
  "Jaggi",
  "Isha",
  "Ishafoundation",
  "Ishayoga",
  "Ishayogacenter",
  "Soundsofisha",
  "Ishalife",
  "Ishaashram",
  "Ishaevents",
  "Ishavolunteers",
  "Ishakriya",
  "Ashramlife",
  "Lingaseva",
  "Innerengineering",
  "Innerengineeringonline",
  "Iecompletion",
  "Bhavaspandana",
  "Shoonyameditation",
  "Shoonya",
  "Samyama",
  "Sadhanapada",
  "Shambhavimahamudra",
  "Cauverycalling",
  "Savesoil",
  "Consciousplanet",
  "Consciousliving",
  "Consciousness",
  "Conscious",
  "Miracleofmind",
  "Adiyogi",
  "Adiyogishiva",
  "Dhyanalinga",
  "Lingabhairavi",
  "Bhairavi",
  "Devi",
  "Shiva",
  "Mahadev",
  "Mahashivratri",
  "Shivaratri",
  "Gurupoornima",
  "Rudraksha",
  "Kailash",
  "Kashi",
  "Sacredspaces",
  "Yoga",
  "Hathayoga",
  "Suryakriya",
  "Suryashakti",
  "Angamardana",
  "Bhutashuddhi",
  "Upayoga",
  "Yogasanas",
  "Kriyayoga",
  "Kriya",
  "Asana",
  "Mudra",
  "Pranayama",
  "Prana",
  "Kundalini",
  "Chakra",
  "Meditation",
  "Meditationpractice",
  "Guidedmeditation",
  "Yogapractice",
  "Spiritualpractice",
  "Dailysadhana",
  "Sadhana",
  "Energybody",
  "Spirituality",
  "Sadhguruquotes",
  "Sadhguruwisdom",
  "Sanatandharma",
  "Omnamahshivaya",
  "Yogi",
  "Yogini",
  "Yogis",
  "Yogic",
  "Mantra",
  "Satsang",
  "Darshan",
  "Samadhi",
  "Mukti",
  "Moksha",
  "Vairagya",
  "Bhakti",
  "Karma",
  "Innerpeace",
  "Bliss",
  "Joyfulliving",
  "Mindfulness",
  "Selfawareness",
  "Selfrealization",
  "Innergrowth",
  "Innertransformation",
  "Spiritualawakening",
  "Wellbeing",
  "Awakening",
  "Enlightenment",
  "Transformation",
  "Stillness",
  "Silence",
  "Devotion",
  "Gratitude",
  "Divineenergy",
  "Presence",
  "Awareness",
  "Culture",
  "Feminine",
  "ஈஷா",
]

const FILTER_CAPTION_KEYWORDS = [
  "Isha",
  "Ishafoundation",
  "Isha Foundation",
  "Ishayoga",
  "Isha Yoga",
  "Ishayogacenter",
  "Isha Yoga Center",
  "Sounds of Isha",
  "Soundsofisha",
  "Isha Volunteers",
  "Isha Life",
  "Isha Ashram",
  "Isha Events",
  "Sacred Spaces",
  "Ashram Life",
  "Coimbatore Ashram",
  "Linga Seva",
  "Sadhguru",
  "Sadguru",
  "Sadhgurujaggivasudev",
  "Sadhguru Jaggi Vasudev",
  "Jaggi",
  "Sadhguru Quotes",
  "Sadhguruquotes",
  "Sadhguru Wisdom",
  "Sadhguruwisdom",
  "Inner Engineering",
  "Innerengineering",
  "Inner Engineering Online",
  "IE Completion",
  "Bhava Spandana",
  "Bhavaspandana",
  "Shoonya Meditation",
  "Shoonyameditation",
  "Shoonya",
  "Samyama",
  "Sadhanapada",
  "Shambhavi Mahamudra",
  "Isha Kriya",
  "Chith Shakti",
  "Cauvery Calling",
  "Cauverycalling",
  "Save Soil",
  "Savesoil",
  "Conscious Planet",
  "Consciousplanet",
  "Conscious Living",
  "Consciousliving",
  "Consciousness",
  "Conscious",
  "Miracle of Mind",
  "Miracleofmind",
  "Adiyogi",
  "Adiyogi Shiva",
  "Adiyogishiva",
  "Dhyanalinga",
  "Linga Bhairavi",
  "Lingabhairavi",
  "Bhairavi",
  "Bhairavi Stuti",
  "Linga Bhairavi Stuti",
  "Bhairavi Utsav",
  "Devi",
  "Shiva",
  "Mahadev",
  "Mahashivratri",
  "Shivaratri",
  "Guru Poornima",
  "Rudraksha",
  "Kashi Yatra",
  "Kailash Manasarovar",
  "Divine Energy",
  "Sanatan Dharma",
  "Om Namah Shivaya",
  "Yoga",
  "Hatha Yoga",
  "Hathayoga",
  "Surya Kriya",
  "Surya Shakti",
  "Angamardana",
  "Bhuta Shuddhi",
  "Upa Yoga",
  "Yogasanas",
  "Kriya Yoga",
  "Kriyayoga",
  "Kriya",
  "Asana",
  "Mudra",
  "Pranayama",
  "Prana",
  "Kundalini",
  "Chakra",
  "Meditation",
  "Meditation Practice",
  "Guided Meditation",
  "Yoga Practice",
  "Spiritual Practice",
  "Daily Sadhana",
  "Sadhana",
  "Energy Body",
  "Spirituality",
  "Mantra",
  "Satsang",
  "Darshan",
  "Samadhi",
  "Mukti",
  "Moksha",
  "Vairagya",
  "Bhakti",
  "Consecrated",
  "Inner Peace",
  "Peace of Mind",
  "Inner Growth",
  "Inner Transformation",
  "Spiritual Awakening",
  "Self Realization",
  "Inner Wellbeing",
  "Higher Self",
  "Bliss",
  "Joyful Living",
  "Mindfulness",
  "Self Awareness",
  "Awakening",
  "Enlightenment",
  "Transformation",
  "Stillness",
  "Silence",
  "Devotion",
  "Gratitude",
  "Presence",
  "Awareness",
  "Culture",
  "Feminine",
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

function getStoredWisdomFilterList(
  key: "hashtags" | "mentions" | "taggedUsers" | "keywords",
  fallback: string[]
) {
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

function formatViewCount(value: number) {
  return Math.round(value).toLocaleString()
}

export function WisdomWarriorsGradeSummaryTable({ selectedSnapshotRunId, monthLabel }: WisdomWarriorsGradeSummaryTableProps) {
  const { data: warriors = [], isLoading: isLoadingWarriors } = useWisdomWarriors()
  const inHouseHashtags = getStoredWisdomFilterList("hashtags", FILTER_HASHTAGS)
  const inHouseMentions = getStoredWisdomFilterList("mentions", FILTER_MENTIONS)
  const inHouseTaggedUsers = getStoredWisdomFilterList("taggedUsers", FILTER_TAGGED_USERS)
  const inHouseKeywords = getStoredWisdomFilterList("keywords", FILTER_CAPTION_KEYWORDS)

  const { data: dedicatedMonthlyViews = [], isLoading: isLoadingDedicatedViews } = useWisdomWarriorsMonthlyViews({
    month: monthLabel ?? "",
    applyFilters: false,
    snapshotRunId: selectedSnapshotRunId,
    category: "Dedicated",
  })

  const { data: inHouseMonthlyViews = [], isLoading: isLoadingInHouseViews } = useWisdomWarriorsMonthlyViews({
    month: monthLabel ?? "",
    applyFilters: true,
    snapshotRunId: selectedSnapshotRunId,
    category: "In-house influencer",
    hashtags: inHouseHashtags,
    mentions: inHouseMentions,
    taggedUsers: inHouseTaggedUsers,
    keywords: inHouseKeywords,
  })

  const gradeSummaries = useMemo<GradeSummary[]>(() => {
    const dedicatedViewsByUsername = new Map(
      dedicatedMonthlyViews.map(item => [item.username.trim().toLowerCase(), Number(item.total_views ?? 0)])
    )
    const inHouseViewsByUsername = new Map(
      inHouseMonthlyViews.map(item => [item.username.trim().toLowerCase(), Number(item.total_views ?? 0)])
    )

    return GRADE_ORDER.map(grade => {
      const dedicatedWarriors = warriors.filter(
        warrior => warrior.grade === grade && warrior.category === "Dedicated"
      )
      const inHouseWarriors = warriors.filter(
        warrior => warrior.grade === grade && warrior.category === "In-house influencer"
      )

      const dedicatedTopChannels = dedicatedWarriors
        .map(warrior => ({
          username: warrior.username,
          views: dedicatedViewsByUsername.get(warrior.username.trim().toLowerCase()) ?? 0,
        }))
        .filter(channel => channel.views > 0)
        .sort((a, b) => b.views - a.views || a.username.localeCompare(b.username))
        .slice(0, 10)

      const inHouseTopChannels = inHouseWarriors
        .map(warrior => ({
          username: warrior.username,
          views: inHouseViewsByUsername.get(warrior.username.trim().toLowerCase()) ?? 0,
        }))
        .filter(channel => channel.views > 0)
        .sort((a, b) => b.views - a.views || a.username.localeCompare(b.username))
        .slice(0, 10)

      const dedicatedTotalViews = dedicatedWarriors.reduce(
        (sum, warrior) => sum + (dedicatedViewsByUsername.get(warrior.username.trim().toLowerCase()) ?? 0),
        0
      )

      const inHouseTotalViews = inHouseWarriors.reduce(
        (sum, warrior) => sum + (inHouseViewsByUsername.get(warrior.username.trim().toLowerCase()) ?? 0),
        0
      )

      return {
        grade,
        dedicatedCount: dedicatedWarriors.length,
        inHouseCount: inHouseWarriors.length,
        dedicatedTotalViews,
        inHouseTotalViews,
        dedicatedTopChannels,
        inHouseTopChannels,
      }
    })
  }, [dedicatedMonthlyViews, inHouseMonthlyViews, warriors])

  const isLoading = isLoadingWarriors || isLoadingDedicatedViews || isLoadingInHouseViews

  return (
    <ChartCard title="Wisdom Warriors Grade Summary">
      <p className="mb-4 text-xs text-gray-400">
        Grade-wise Dedicated and IHI counts, top 10 channels by views, and total views for {monthLabel ?? "current month"}.
      </p>
      <p className="mb-4 text-[11px] text-gray-500">
        Data source: post_snapshot (run_id: {selectedSnapshotRunId ?? "N/A"}) • IHI views use hashtag, mention, tagged-user, and caption-keyword filters.
      </p>

      {isLoading ? (
        <div className="h-64 animate-pulse rounded-xl bg-gray-800/60" />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-indigo-500/20 bg-gradient-to-b from-indigo-950/20 via-gray-900/40 to-gray-950/50">
          <table className="min-w-[980px] w-full text-sm">
            <thead>
              <tr className="bg-indigo-950/40 text-indigo-100">
                {gradeSummaries.map(summary => (
                  <th key={summary.grade} className="border-b border-r border-indigo-500/20 px-3 py-3 text-left font-semibold last:border-r-0">
                    <span
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${GRADE_BADGE_STYLES[summary.grade]}`}
                    >
                      Grade {summary.grade}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr className="align-top text-gray-200">
                {gradeSummaries.map(summary => (
                  <td key={summary.grade} className="border-b border-r border-indigo-500/15 px-3 py-3 align-top last:border-r-0">
                    <div className="rounded-lg border border-indigo-500/20 bg-gray-950/60 px-3 py-2">
                      <p className="text-[11px] uppercase tracking-[0.14em] text-indigo-200/80">Profiles</p>
                      <p className="mt-1 text-white">Dedicated: {summary.dedicatedCount.toLocaleString()}</p>
                      <p className="text-white">IHI: {summary.inHouseCount.toLocaleString()}</p>
                    </div>
                  </td>
                ))}
              </tr>
              <tr className="align-top text-gray-200">
                {gradeSummaries.map(summary => (
                  <td key={summary.grade} className="border-b border-r border-indigo-500/15 px-3 py-3 align-top last:border-r-0">
                    <div className="rounded-lg border border-fuchsia-500/20 bg-fuchsia-950/10 px-3 py-2">
                      <p className="text-[11px] uppercase tracking-[0.14em] text-fuchsia-200/80">Top 10 Dedicated (views)</p>
                    {summary.dedicatedTopChannels.length === 0 ? (
                      <p className="mt-1 text-gray-400">No Dedicated channels</p>
                    ) : (
                      <ol className="mt-2 space-y-1 text-xs text-gray-100">
                        {summary.dedicatedTopChannels.map(channel => (
                          <li key={`${summary.grade}-dedicated-${channel.username}`} className="flex items-center justify-between gap-2">
                            <span className="truncate">@{channel.username}</span>
                            <span className="text-indigo-100">{formatViewCount(channel.views)}</span>
                          </li>
                        ))}
                      </ol>
                    )}
                    </div>

                    <div className="mt-3 rounded-lg border border-indigo-500/20 bg-indigo-950/10 px-3 py-2">
                      <p className="text-[11px] uppercase tracking-[0.14em] text-indigo-200/80">Top 10 IHI (views)</p>
                      {summary.inHouseTopChannels.length === 0 ? (
                        <p className="mt-1 text-gray-400">No IHI channels</p>
                      ) : (
                        <ol className="mt-2 space-y-1 text-xs text-gray-100">
                          {summary.inHouseTopChannels.map(channel => (
                            <li key={`${summary.grade}-in-house-${channel.username}`} className="flex items-center justify-between gap-2">
                              <span className="truncate">@{channel.username}</span>
                              <span className="text-indigo-100">{formatViewCount(channel.views)}</span>
                            </li>
                          ))}
                        </ol>
                      )}
                    </div>
                  </td>
                ))}
              </tr>
              <tr className="align-top text-gray-200">
                {gradeSummaries.map(summary => (
                  <td key={summary.grade} className="border-r border-indigo-500/15 px-3 py-3 align-top last:border-r-0">
                    <div className="rounded-lg border border-indigo-500/20 bg-gray-950/60 px-3 py-2">
                      <p className="text-[11px] uppercase tracking-[0.14em] text-indigo-200/80">Total Views</p>
                      <p className="mt-1 text-white">Dedicated: {formatViewCount(summary.dedicatedTotalViews)}</p>
                      <p className="text-white">IHI: {formatViewCount(summary.inHouseTotalViews)}</p>
                    </div>
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </ChartCard>
  )
}