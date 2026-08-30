import { useState, useMemo } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { 
  X, 
  RefreshCw, 
  CheckCircle2, 
  AlertTriangle, 
  ExternalLink, 
  Plus, 
  CheckSquare, 
  Square,
  Search,
  FileSpreadsheet,
  Link2Off,
  UserX,
  AlertOctagon,
  ArrowRight,
  Database,
  Users
} from "lucide-react"
import { 
  fetchGoogleSheetsSyncPreview, 
  applyGoogleSheetsSync, 
  type GoogleSheetsSyncItem 
} from "../../api/wisdomWarriors"

interface Props {
  isOpen: boolean
  onClose: () => void
}

type SyncSource = "dedicated" | "ihi"
type StatusTab = "all" | "NEW_CHANNEL" | "HANDLE_CHANGED" | "BROKEN_OR_DELETED" | "LINK_INVALID" | "CHANNEL_DELETED" | "ALREADY_TRACKED"

export function GoogleSheetSyncModal({ isOpen, onClose }: Props) {
  const queryClient = useQueryClient()
  const [selectedSource, setSelectedSource] = useState<SyncSource>("dedicated")
  const [selectedGradeTab, setSelectedGradeTab] = useState<string>("all")
  const [activeStatusTab, setActiveStatusTab] = useState<StatusTab>("all")
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedUsernames, setSelectedUsernames] = useState<Set<string>>(new Set())

  const { 
    data: syncData, 
    isLoading, 
    isFetching, 
    refetch, 
    error 
  } = useQuery({
    queryKey: ["googleSheetsSyncPreview", selectedSource],
    queryFn: () => fetchGoogleSheetsSyncPreview(selectedSource),
    enabled: isOpen,
    refetchOnWindowFocus: false,
  })

  const applyMutation = useMutation({
    mutationFn: (itemsToAdd: GoogleSheetsSyncItem[]) => {
      const payload = itemsToAdd.map(item => ({
        username: item.username,
        grade: item.grade,
        category: item.category,
      }))
      return applyGoogleSheetsSync(payload)
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["wisdomWarriors"] })
      queryClient.invalidateQueries({ queryKey: ["googleSheetsSyncPreview"] })
      alert(`Successfully added ${res.added_count} new channel(s) to Wisdom Warriors!`)
      setSelectedUsernames(new Set())
      onClose()
    },
    onError: (err: any) => {
      alert(`Failed to apply sync: ${err.message}`)
    },
  })

  // Dynamic Grade Tabs based on the active dataset
  const dynamicGradeTabs = useMemo(() => {
    if (!syncData?.items) return [{ id: "all", label: "All Tabs", count: 0 }]
    
    if (selectedSource === "dedicated") {
      const fixedOrder = ["all", "A", "B", "C", "D", "E", "Inactive"]
      return fixedOrder.map(gid => {
        if (gid === "all") return { id: "all", label: "All Tabs", count: syncData.items.length }
        const count = syncData.items.filter(it => it.grade === gid).length
        return { id: gid, label: gid === "Inactive" ? "Inactive" : `Grade ${gid}`, count }
      })
    } else {
      // IHI Master tabs
      const uniqueGrades = Array.from(new Set(syncData.items.map(it => it.grade))).filter(Boolean)
      const tabs = [{ id: "all", label: "All (IHI Master)", count: syncData.items.length }]
      uniqueGrades.forEach(g => {
        const count = syncData.items.filter(it => it.grade === g).length
        tabs.push({ id: g, label: g.startsWith("Grade") ? g : `Grade ${g}`, count })
      })
      return tabs
    }
  }, [syncData, selectedSource])

  // Items filtered by Grade Tab first
  const gradeFilteredItems = useMemo(() => {
    if (!syncData?.items) return []
    if (selectedGradeTab === "all") return syncData.items
    return syncData.items.filter(item => item.grade === selectedGradeTab)
  }, [syncData, selectedGradeTab])

  // Status summaries within selected Grade Tab
  const statusCounts = useMemo(() => {
    const summary = {
      total: gradeFilteredItems.length,
      new_channels: 0,
      handle_changed: 0,
      link_invalid: 0,
      channel_deleted: 0,
      broken_or_deleted: 0,
      already_tracked: 0,
    }
    gradeFilteredItems.forEach(item => {
      if (item.case_type === "NEW_CHANNEL") summary.new_channels += 1
      else if (item.case_type === "HANDLE_CHANGED") summary.handle_changed += 1
      else if (item.case_type === "LINK_INVALID") {
        summary.link_invalid += 1
        summary.broken_or_deleted += 1
      }
      else if (item.case_type === "CHANNEL_DELETED") {
        summary.channel_deleted += 1
        summary.broken_or_deleted += 1
      }
      else if (item.case_type === "ALREADY_TRACKED") summary.already_tracked += 1
    })
    return summary
  }, [gradeFilteredItems])

  // Final items filtered by Grade Tab + Status Tab + Search Query
  const finalFilteredItems = useMemo(() => {
    return gradeFilteredItems.filter(item => {
      // Status filter
      if (activeStatusTab === "BROKEN_OR_DELETED") {
        if (item.case_type !== "LINK_INVALID" && item.case_type !== "CHANNEL_DELETED") {
          return false
        }
      } else if (activeStatusTab !== "all" && item.case_type !== activeStatusTab) {
        return false
      }
      // Search filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const idMatch = item.channel_id.toLowerCase().includes(q)
        const nameMatch = item.creator_name.toLowerCase().includes(q)
        const handleMatch = item.username.toLowerCase().includes(q)
        const rawMatch = item.raw_input.toLowerCase().includes(q)
        if (!idMatch && !nameMatch && !handleMatch && !rawMatch) {
          return false
        }
      }
      return true
    })
  }, [gradeFilteredItems, activeStatusTab, searchQuery])

  // Selectable new channels in current view
  const selectableNewChannels = useMemo(() => {
    return finalFilteredItems.filter(item => item.can_add && item.username)
  }, [finalFilteredItems])

  const isAllSelected = selectableNewChannels.length > 0 && 
    selectableNewChannels.every(item => selectedUsernames.has(item.username))

  const toggleSelectAll = () => {
    if (isAllSelected) {
      const next = new Set(selectedUsernames)
      selectableNewChannels.forEach(item => next.delete(item.username))
      setSelectedUsernames(next)
    } else {
      const next = new Set(selectedUsernames)
      selectableNewChannels.forEach(item => next.add(item.username))
      setSelectedUsernames(next)
    }
  }

  const toggleSelectItem = (username: string) => {
    const next = new Set(selectedUsernames)
    if (next.has(username)) {
      next.delete(username)
    } else {
      next.add(username)
    }
    setSelectedUsernames(next)
  }

  const handleSourceChange = (newSource: SyncSource) => {
    if (newSource !== selectedSource) {
      setSelectedSource(newSource)
      setSelectedGradeTab("all")
      setActiveStatusTab("all")
      setSelectedUsernames(new Set())
    }
  }

  const handleApply = () => {
    if (!syncData?.items) return
    const itemsToAdd = syncData.items.filter(
      item => selectedUsernames.has(item.username) && item.can_add
    )
    if (itemsToAdd.length === 0) {
      alert("Please select at least one new channel to add.")
      return
    }
    applyMutation.mutate(itemsToAdd)
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-5xl my-auto flex flex-col max-h-[90vh] shadow-2xl overflow-hidden">
        
        {/* Modal Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-800 bg-gray-900/90 sticky top-0 z-10">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="p-2 bg-emerald-950/80 border border-emerald-700/50 rounded-lg text-emerald-400">
                <FileSpreadsheet className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  Sync Channels from Google Sheets
                </h2>
                <p className="text-xs text-gray-400">
                  {selectedSource === "dedicated" 
                    ? "Dedicated Master Database (Grades A–E & Inactive) • Missing links filtered out"
                    : "IHI Master Database (In-house Influencers) • Missing links filtered out"}
                </p>
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={() => refetch()}
              disabled={isLoading || isFetching}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs rounded-lg border border-gray-700 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin text-purple-400" : ""}`} />
              {isFetching ? "Syncing..." : "Refresh Sheet"}
            </button>
            <button
              onClick={onClose}
              className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Database Source Switcher (Dedicated vs IHI) */}
        <div className="flex items-center gap-3 px-5 py-2.5 bg-gray-950/90 border-b border-gray-800">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
            <Database className="w-3.5 h-3.5 text-purple-400" /> Database:
          </span>
          <div className="flex items-center gap-1 bg-gray-900 p-1 rounded-xl border border-gray-800">
            <button
              onClick={() => handleSourceChange("dedicated")}
              className={`flex items-center gap-1.5 px-3 py-1 text-xs font-semibold rounded-lg transition-all ${
                selectedSource === "dedicated"
                  ? "bg-purple-600 text-white shadow-md shadow-purple-950/50"
                  : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60"
              }`}
            >
              <Users className="w-3.5 h-3.5" /> Dedicated Master
            </button>
            <button
              onClick={() => handleSourceChange("ihi")}
              className={`flex items-center gap-1.5 px-3 py-1 text-xs font-semibold rounded-lg transition-all ${
                selectedSource === "ihi"
                  ? "bg-purple-600 text-white shadow-md shadow-purple-950/50"
                  : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60"
              }`}
            >
              <Users className="w-3.5 h-3.5" /> IHI Master (In-house)
            </button>
          </div>
        </div>

        {/* Primary Grade Tab Navigation */}
        <div className="flex items-center gap-2 px-5 pt-3 pb-0 bg-gray-950/80 border-b border-gray-800 overflow-x-auto">
          {dynamicGradeTabs.map(tab => {
            const isSelected = selectedGradeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setSelectedGradeTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-all whitespace-nowrap ${
                  isSelected 
                    ? "border-emerald-500 text-white bg-emerald-950/20" 
                    : "border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-900/50"
                }`}
              >
                <span>{tab.label}</span>
                <span className={`px-1.5 py-0.2 rounded-full text-[10px] ${
                  isSelected ? "bg-emerald-600 text-white" : "bg-gray-800 text-gray-400"
                }`}>
                  {tab.count}
                </span>
              </button>
            )
          })}
        </div>

        {/* KPI Summary Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-5 pb-3 bg-gray-950/40 border-b border-gray-800">
          <div 
            onClick={() => setActiveStatusTab("NEW_CHANNEL")}
            className={`p-3 rounded-xl border cursor-pointer transition-all ${
              activeStatusTab === "NEW_CHANNEL" 
                ? "bg-emerald-950/40 border-emerald-500/60 shadow-lg shadow-emerald-950/30" 
                : "bg-gray-900/80 border-gray-800 hover:border-gray-700"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> New Channels
              </span>
              <span className="text-lg font-bold text-white">{statusCounts.new_channels}</span>
            </div>
            <p className="text-[11px] text-gray-400">Active & ready to add (Checkbox)</p>
          </div>

          <div 
            onClick={() => setActiveStatusTab("HANDLE_CHANGED")}
            className={`p-3 rounded-xl border cursor-pointer transition-all ${
              activeStatusTab === "HANDLE_CHANGED" 
                ? "bg-amber-950/40 border-amber-500/60 shadow-lg shadow-amber-950/30" 
                : "bg-gray-900/80 border-gray-800 hover:border-gray-700"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-amber-400 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" /> Handle Changed
              </span>
              <span className="text-lg font-bold text-white">{statusCounts.handle_changed}</span>
            </div>
            <p className="text-[11px] text-gray-400">Updated handle in sheet</p>
          </div>

          <div 
            onClick={() => setActiveStatusTab("BROKEN_OR_DELETED")}
            className={`p-3 rounded-xl border cursor-pointer transition-all ${
              activeStatusTab === "BROKEN_OR_DELETED" 
                ? "bg-rose-950/50 border-rose-500/60 shadow-lg shadow-rose-950/30" 
                : "bg-gray-900/80 border-gray-800 hover:border-gray-700"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-rose-400 flex items-center gap-1">
                <AlertOctagon className="w-3.5 h-3.5" /> Broken / Deleted
              </span>
              <span className="text-lg font-bold text-white">{statusCounts.broken_or_deleted}</span>
            </div>
            <p className="text-[11px] text-gray-400">
              {statusCounts.link_invalid} Invalid • {statusCounts.channel_deleted} Deleted
            </p>
          </div>

          <div 
            onClick={() => setActiveStatusTab("ALREADY_TRACKED")}
            className={`p-3 rounded-xl border cursor-pointer transition-all ${
              activeStatusTab === "ALREADY_TRACKED" 
                ? "bg-purple-950/40 border-purple-500/60 shadow-lg shadow-purple-950/30" 
                : "bg-gray-900/80 border-gray-800 hover:border-gray-700"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-purple-400 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> Already Tracked
              </span>
              <span className="text-lg font-bold text-white">{statusCounts.already_tracked}</span>
            </div>
            <p className="text-[11px] text-gray-400">Up to date in system</p>
          </div>
        </div>

        {/* Status Filter Bar & Search */}
        <div className="p-4 flex flex-col sm:flex-row items-center justify-between gap-3 border-b border-gray-800 bg-gray-900">
          <div className="flex items-center gap-1 bg-gray-950 p-1 rounded-xl border border-gray-800 w-full sm:w-auto overflow-x-auto">
            <button
              onClick={() => setActiveStatusTab("all")}
              className={`px-3 py-1 text-xs rounded-lg font-medium transition-colors ${
                activeStatusTab === "all" ? "bg-purple-600 text-white" : "text-gray-400 hover:text-white"
              }`}
            >
              All ({statusCounts.total})
            </button>
            <button
              onClick={() => setActiveStatusTab("NEW_CHANNEL")}
              className={`px-3 py-1 text-xs rounded-lg font-medium transition-colors ${
                activeStatusTab === "NEW_CHANNEL" ? "bg-emerald-600 text-white" : "text-gray-400 hover:text-white"
              }`}
            >
              New Channels ({statusCounts.new_channels})
            </button>
            <button
              onClick={() => setActiveStatusTab("HANDLE_CHANGED")}
              className={`px-3 py-1 text-xs rounded-lg font-medium transition-colors ${
                activeStatusTab === "HANDLE_CHANGED" ? "bg-amber-600 text-white" : "text-gray-400 hover:text-white"
              }`}
            >
              Handle Changed ({statusCounts.handle_changed})
            </button>
            <button
              onClick={() => setActiveStatusTab("BROKEN_OR_DELETED")}
              className={`px-3 py-1 text-xs rounded-lg font-medium transition-colors ${
                activeStatusTab === "BROKEN_OR_DELETED" ? "bg-rose-600 text-white" : "text-gray-400 hover:text-white"
              }`}
            >
              Broken / Deleted ({statusCounts.broken_or_deleted})
            </button>
          </div>

          <div className="relative w-full sm:w-64">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-gray-400" />
            <input
              type="text"
              placeholder="Search ID, name, or handle..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 bg-gray-950 border border-gray-800 rounded-xl text-xs text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
            />
          </div>
        </div>

        {/* Table Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-16 text-gray-400">
              <RefreshCw className="w-8 h-8 animate-spin text-purple-400 mb-3" />
              <p className="text-sm font-medium">
                Scanning {selectedSource === "dedicated" ? "Dedicated Master Database (6 Tabs)" : "IHI Master Database"}...
              </p>
              <p className="text-xs text-gray-500 mt-1">Checking link reachability and verifying Instagram profiles</p>
            </div>
          ) : error ? (
            <div className="p-8 text-center text-red-400">
              <AlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-80" />
              <p className="font-semibold text-sm">Failed to fetch Google Sheet</p>
              <p className="text-xs text-gray-500 mt-1">{(error as any).message}</p>
            </div>
          ) : finalFilteredItems.length === 0 ? (
            <div className="py-16 text-center text-gray-500 text-sm">
              No channel rows found for {selectedGradeTab === "all" ? "the selected filter" : `Tab ${selectedGradeTab} with this filter`}.
            </div>
          ) : (
            <div className="border border-gray-800 rounded-xl overflow-hidden bg-gray-950/40">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-gray-800/60 text-gray-400 border-b border-gray-800">
                    <th className="p-3 w-10 text-center">
                      {selectableNewChannels.length > 0 && (
                        <button 
                          onClick={toggleSelectAll}
                          title={isAllSelected ? "Deselect All" : "Select All New Channels in this Tab"}
                          className="text-gray-400 hover:text-white"
                        >
                          {isAllSelected ? (
                            <CheckSquare className="w-4 h-4 text-emerald-400" />
                          ) : (
                            <Square className="w-4 h-4" />
                          )}
                        </button>
                      )}
                    </th>
                    <th className="p-3 font-semibold">Sheet Tab</th>
                    <th className="p-3 font-semibold">Channel ID</th>
                    <th className="p-3 font-semibold">Creator Name</th>
                    <th className="p-3 font-semibold">Instagram Handle / URL</th>
                    <th className="p-3 font-semibold text-center">Grade</th>
                    <th className="p-3 font-semibold text-center">Category</th>
                    <th className="p-3 font-semibold">Status / Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/60">
                  {finalFilteredItems.map((item, idx) => {
                    const isSelected = selectedUsernames.has(item.username)
                    return (
                      <tr 
                        key={`${item.channel_id}_${item.username}_${idx}`}
                        className={`hover:bg-gray-800/30 transition-colors ${
                          isSelected ? "bg-emerald-950/20" : ""
                        }`}
                      >
                        {/* Checkbox */}
                        <td className="p-3 text-center">
                          {item.can_add ? (
                            <button
                              onClick={() => toggleSelectItem(item.username)}
                              className="text-gray-400 hover:text-white transition-colors"
                            >
                              {isSelected ? (
                                <CheckSquare className="w-4 h-4 text-emerald-400" />
                              ) : (
                                <Square className="w-4 h-4" />
                              )}
                            </button>
                          ) : (
                            <span className="text-gray-600 block text-center">—</span>
                          )}
                        </td>

                        {/* Sheet Tab Badge */}
                        <td className="p-3 whitespace-nowrap">
                          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-gray-800/80 text-gray-300 border border-gray-700">
                            {item.tab_name}
                          </span>
                        </td>

                        {/* Channel ID */}
                        <td className="p-3 font-mono font-medium text-gray-300">
                          {item.channel_id}
                        </td>

                        {/* Creator Name */}
                        <td className="p-3 text-gray-200 font-medium">
                          {item.creator_name || "—"}
                        </td>

                        {/* Instagram Handle / Link */}
                        <td className="p-3">
                          {item.case_type === "HANDLE_CHANGED" && (item as any).old_username ? (
                            <div className="flex items-center gap-1.5 font-medium text-xs">
                              <span className="text-gray-400 line-through">@{(item as any).old_username}</span>
                              <ArrowRight className="w-3 h-3 text-amber-400" />
                              <a
                                href={item.instagram_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-amber-400 hover:text-amber-300 font-semibold inline-flex items-center gap-1"
                              >
                                @{item.username}
                                <ExternalLink className="w-3 h-3 opacity-60" />
                              </a>
                            </div>
                          ) : item.username ? (
                            <a
                              href={item.instagram_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-purple-400 hover:text-purple-300 font-medium inline-flex items-center gap-1"
                            >
                              @{item.username}
                              <ExternalLink className="w-3 h-3 opacity-60" />
                            </a>
                          ) : (
                            <span className="text-gray-500 italic truncate max-w-[200px] block" title={item.raw_input}>
                              {item.raw_input || "—"}
                            </span>
                          )}
                        </td>

                        {/* Grade */}
                        <td className="p-3 text-center">
                          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-gray-800 text-gray-300 border border-gray-700">
                            {item.grade === "Inactive" ? "Inactive" : item.grade.startsWith("Grade") ? item.grade : `Grade ${item.grade}`}
                          </span>
                        </td>

                        {/* Category */}
                        <td className="p-3 text-center">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-medium border ${
                            item.category === "In-house influencer"
                              ? "bg-blue-950/60 text-blue-300 border-blue-800/40"
                              : "bg-purple-950/60 text-purple-300 border-purple-800/40"
                          }`}>
                            {item.category}
                          </span>
                        </td>

                        {/* Status Badge */}
                        <td className="p-3">
                          {item.case_type === "NEW_CHANNEL" && (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-700/60">
                              <CheckCircle2 className="w-3 h-3" /> New Channel
                            </span>
                          )}
                          {item.case_type === "HANDLE_CHANGED" && (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-amber-950/80 text-amber-300 border border-amber-700/60">
                              <AlertTriangle className="w-3 h-3" /> Handle Changed
                            </span>
                          )}
                          {item.case_type === "LINK_INVALID" && (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium bg-rose-950/60 text-rose-400 border border-rose-800/40">
                              <Link2Off className="w-3 h-3" /> Link Invalid
                            </span>
                          )}
                          {item.case_type === "CHANNEL_DELETED" && (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium bg-red-950/60 text-red-400 border border-red-800/40">
                              <UserX className="w-3 h-3" /> Channel Deleted / Not Found
                            </span>
                          )}
                          {item.case_type === "ALREADY_TRACKED" && (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium bg-gray-800 text-gray-400 border border-gray-700">
                              Already Tracked
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Modal Footer / Actions */}
        <div className="flex items-center justify-between p-4 border-t border-gray-800 bg-gray-900">
          <div className="text-xs text-gray-400 flex items-center gap-2">
            <span>
              Selected: <strong className="text-emerald-400">{selectedUsernames.size}</strong> new channels
            </span>
            <span className="text-gray-500">
              ({selectedSource === "dedicated" ? "Dedicated Master" : "IHI Master"})
            </span>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-medium rounded-xl border border-gray-700 transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleApply}
              disabled={selectedUsernames.size === 0 || applyMutation.isPending}
              className="flex items-center gap-2 px-5 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-800 disabled:text-gray-600 text-white text-xs font-semibold rounded-xl shadow-lg shadow-emerald-950/50 transition-all"
            >
              {applyMutation.isPending ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Plus className="w-4 h-4" />
              )}
              Add Selected Channels ({selectedUsernames.size})
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
