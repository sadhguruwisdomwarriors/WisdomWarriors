import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, X, UserPlus, Users, ChevronDown, ChevronUp, Search } from "lucide-react";
import { 
  addCreator,
  deleteCreator,
  addChannel, 
  removeChannel, 
  fetchAvailableProfiles, 
  fetchAvailableYoutubeChannels,
  autoCalculateUnitMetrics,
  type MicroUnit 
} from "../../api/microUnits";

const YoutubeIcon = ({ size = 16, className = "" }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className}>
    <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
  </svg>
);

const InstagramIcon = ({ size = 16, className = "" }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect>
    <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path>
    <line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line>
  </svg>
);

interface ManageChannelsModalProps {
  unit: MicroUnit;
  onClose: () => void;
}

export default function ManageChannelsModal({ unit, onClose }: ManageChannelsModalProps) {
  const [newCreatorName, setNewCreatorName] = useState("");
  const [activeCreatorId, setActiveCreatorId] = useState<number | string | null>(null);
  
  // Channel add states for active creator
  const [platform, setPlatform] = useState<"INSTAGRAM" | "YOUTUBE">("INSTAGRAM");
  const [selectedProfile, setSelectedProfile] = useState("");
  const [igSearchTerm, setIgSearchTerm] = useState("");

  const [selectedYtChannel, setSelectedYtChannel] = useState("");
  const [ytSearchTerm, setYtSearchTerm] = useState("");
  const [isCalculating, setIsCalculating] = useState(false);

  const queryClient = useQueryClient();

  const handleDone = async () => {
    setIsCalculating(true);
    try {
      await autoCalculateUnitMetrics(unit.id);
    } catch (err) {
      console.warn("Auto-calc error on done:", err);
    } finally {
      queryClient.invalidateQueries({ queryKey: ["microUnits"] });
      queryClient.invalidateQueries({ queryKey: ["microUnitDashboard"] });
      queryClient.invalidateQueries({ queryKey: ["myUnit"] });
      setIsCalculating(false);
      onClose();
    }
  };

  const { data: availableProfiles = [], isLoading: loadingProfiles } = useQuery({
    queryKey: ["availableProfiles"],
    queryFn: fetchAvailableProfiles,
  });

  const { data: availableYtChannels = [], isLoading: loadingYtChannels } = useQuery({
    queryKey: ["availableYoutubeChannels"],
    queryFn: fetchAvailableYoutubeChannels,
  });

  // Creator Mutations
  const addCreatorMutation = useMutation({
    mutationFn: (name: string) => addCreator(unit.id, { name }),
    onSuccess: (newCreator) => {
      queryClient.invalidateQueries({ queryKey: ["microUnits"] });
      setNewCreatorName("");
      setActiveCreatorId(newCreator.id);
    },
    onError: (err: any) => {
      alert(`Error creating creator: ${err.message}`);
    },
  });

  const deleteCreatorMutation = useMutation({
    mutationFn: (creatorId: number) => deleteCreator(unit.id, creatorId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["microUnits"] });
    },
    onError: (err: any) => {
      alert(`Error deleting creator: ${err.message}`);
    },
  });

  // Channel Mutations
  const addChannelMutation = useMutation({
    mutationFn: (body: { 
      creator_id?: number;
      platform: "INSTAGRAM" | "YOUTUBE";
      username: string; 
      instagram_id?: string; 
      creator_name?: string;
      channel_title?: string;
    }) => addChannel(unit.id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["microUnits"] });
      setSelectedProfile("");
      setIgSearchTerm("");
      setSelectedYtChannel("");
      setYtSearchTerm("");
    },
    onError: (err: any) => {
      alert(`Error adding channel: ${err.message}`);
    },
  });

  const removeChannelMutation = useMutation({
    mutationFn: (channelId: number) => removeChannel(unit.id, channelId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["microUnits"] });
    },
    onError: (err: any) => {
      alert(`Error removing channel: ${err.message}`);
    },
  });

  const handleCreateCreatorSubmit = (e: FormEvent) => {
    e.preventDefault();
    const name = newCreatorName.trim();
    if (!name) return;
    addCreatorMutation.mutate(name);
  };

  const handleAttachChannel = (creatorId?: number, creatorName?: string) => {
    if (platform === "INSTAGRAM") {
      if (!selectedProfile) return;
      const prof = availableProfiles.find(p => p.username.toLowerCase() === selectedProfile.toLowerCase());
      if (prof) {
        addChannelMutation.mutate({
          creator_id: creatorId,
          platform: "INSTAGRAM",
          username: prof.username,
          instagram_id: prof.id,
          creator_name: creatorName || prof.creator_name || `@${prof.username}`,
          channel_title: `@${prof.username}`,
        });
      }
    } else {
      // YouTube
      if (!selectedYtChannel) return;
      const yt = availableYtChannels.find(c => (c.youtube_channel_id && c.youtube_channel_id === selectedYtChannel) || (c.id && c.id === selectedYtChannel));
      if (yt) {
        addChannelMutation.mutate({
          creator_id: creatorId,
          platform: "YOUTUBE",
          username: yt.youtube_channel_id || yt.id,
          instagram_id: yt.youtube_channel_id || yt.id,
          creator_name: creatorName || yt.title || "YouTube Creator",
          channel_title: yt.title,
        });
      }
    }
  };

  const pocName = unit.poc_name || unit.poc?.full_name || null;

  // Group existing channels by creator
  const explicitCreators = unit.creators || [];
  const creatorMap: Record<string, { id?: number; name: string; isPoc?: boolean; channels: typeof unit.channels }> = {};

  // If POC exists, initialize POC first
  if (pocName) {
    const existingPocCreator = explicitCreators.find(c => c.name.toLowerCase() === pocName.toLowerCase());
    creatorMap[pocName] = { 
      id: existingPocCreator?.id, 
      name: pocName, 
      isPoc: true, 
      channels: [] 
    };
  }

  // Initialize from explicit creators
  explicitCreators.forEach(cr => {
    const isPoc = pocName && cr.name.toLowerCase() === pocName.toLowerCase();
    if (!creatorMap[cr.name]) {
      creatorMap[cr.name] = { id: cr.id, name: cr.name, isPoc: !!isPoc, channels: [] };
    } else {
      creatorMap[cr.name].id = cr.id;
      if (isPoc) creatorMap[cr.name].isPoc = true;
    }
  });

  // Distribute channels
  unit.channels.forEach(ch => {
    const cName = ch.creator_name || ch.channel_title || ch.username || "Unassigned Creator";
    const isPoc = pocName && cName.toLowerCase() === pocName.toLowerCase();
    if (!creatorMap[cName]) {
      creatorMap[cName] = { id: ch.creator_id || undefined, name: cName, isPoc: !!isPoc, channels: [] };
    }
    creatorMap[cName].channels.push(ch);
  });

  // Sort so POC appears first, followed by alphabetical creators
  const creatorList = Object.values(creatorMap).sort((a, b) => {
    if (a.isPoc && !b.isPoc) return -1;
    if (!a.isPoc && b.isPoc) return 1;
    return a.name.localeCompare(b.name);
  });

  // Filter already assigned handles
  const existingKeys = new Set(unit.channels.map(c => `${c.platform || 'INSTAGRAM'}_${c.username.toLowerCase()}`));
  
  const unassignedProfiles = availableProfiles.filter(
    p => !existingKeys.has(`INSTAGRAM_${p.username.toLowerCase()}`)
  );

  const filteredIgProfiles = unassignedProfiles
    .filter(p => !igSearchTerm || p.username.toLowerCase().includes(igSearchTerm.toLowerCase()) || (p.creator_name && p.creator_name.toLowerCase().includes(igSearchTerm.toLowerCase())));

  const filteredYtChannels = availableYtChannels
    .filter(c => !existingKeys.has(`YOUTUBE_${(c.youtube_channel_id || c.id).toLowerCase()}`))
    .filter(c => !ytSearchTerm || c.title.toLowerCase().includes(ytSearchTerm.toLowerCase()) || c.custom_url.toLowerCase().includes(ytSearchTerm.toLowerCase()));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-2xl shadow-2xl my-auto max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex justify-between items-center mb-4 pb-3 border-b border-gray-800 flex-shrink-0">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <span>Edit Creators & Channels</span>
              <span className="bg-purple-950 text-purple-300 text-xs px-2.5 py-0.5 rounded-full border border-purple-800">
                {unit.name}
              </span>
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Add Content Creators & POC channels, then assign multiple YouTube and Instagram accounts to each
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <div className="overflow-y-auto flex-1 pr-1 space-y-5">
          {/* POC Quick Channels Banner (if POC assigned) */}
          {pocName && (
            <div className="bg-gradient-to-r from-purple-950/40 via-purple-900/20 to-gray-950 border border-purple-700/40 rounded-xl p-3.5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-sm">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-purple-900/60 text-purple-200 border border-purple-600/50 flex items-center justify-center text-sm font-bold shadow-inner flex-shrink-0">
                  {pocName.charAt(0).toUpperCase()}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-white font-bold text-sm">{pocName}</span>
                    <span className="bg-purple-950 text-purple-300 text-[10px] font-bold px-2 py-0.5 rounded-md border border-purple-700/60 uppercase tracking-wide">
                      POC
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Add & manage YouTube and Instagram channels for this unit's POC
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setActiveCreatorId(activeCreatorId === (creatorMap[pocName]?.id || pocName) ? null : (creatorMap[pocName]?.id || pocName))}
                className="px-3.5 py-1.5 bg-purple-700 hover:bg-purple-600 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors flex items-center gap-1.5 flex-shrink-0"
              >
                <Plus size={14} />
                {activeCreatorId === (creatorMap[pocName]?.id || pocName) ? "Close" : "+ Add POC Channels"}
              </button>
            </div>
          )}

          {/* STEP 1: Add New Content Creator Form */}
          <div className="bg-gray-950/80 border border-purple-900/40 rounded-xl p-4 shadow-sm">
            <h3 className="text-xs font-bold text-purple-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <UserPlus size={14} />
              Add Content Creator to this Unit
            </h3>
            <form onSubmit={handleCreateCreatorSubmit} className="flex gap-2">
              <input
                type="text"
                placeholder="Enter Content Creator Name (e.g. Sanjeev Yogii, Priya Sharma)"
                className="flex-1 bg-gray-900 border border-gray-700 rounded-xl px-3.5 py-2 text-white text-sm focus:outline-none focus:border-purple-500 placeholder-gray-600"
                value={newCreatorName}
                onChange={(e) => setNewCreatorName(e.target.value)}
                required
              />
              <button
                type="submit"
                disabled={addCreatorMutation.isPending || !newCreatorName.trim()}
                className="px-4 py-2 bg-purple-700 hover:bg-purple-600 text-white font-medium rounded-xl text-sm flex items-center gap-1.5 transition-colors disabled:opacity-50 shadow-md shadow-purple-950 flex-shrink-0"
              >
                <Plus size={16} />
                {addCreatorMutation.isPending ? "Adding..." : "Add Creator"}
              </button>
            </form>
          </div>

          {/* STEP 2: Content Creators & Channels List */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                <Users size={14} />
                Creators & POC in this Unit ({creatorList.length})
              </h3>
              <span className="text-xs text-gray-500">
                Total Channels: {unit.channels.length}
              </span>
            </div>

            {creatorList.length === 0 ? (
              <div className="p-8 bg-gray-950/40 rounded-xl border border-dashed border-gray-800 text-center text-gray-500 text-sm space-y-1">
                <p className="font-medium text-gray-400">No content creators added yet.</p>
                <p className="text-xs text-gray-600">Type a creator's name above and click "Add Creator" to start.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {creatorList.map((creator, cIdx) => {
                  const isExpanded = activeCreatorId === (creator.id || creator.name);
                  const isPoc = !!creator.isPoc;
                  const ytCount = creator.channels.filter(c => (c.platform || "INSTAGRAM").toUpperCase() === "YOUTUBE").length;
                  const igCount = creator.channels.filter(c => (c.platform || "INSTAGRAM").toUpperCase() === "INSTAGRAM").length;

                  return (
                    <div
                      key={cIdx}
                      className={`border rounded-xl overflow-hidden shadow-md transition-all ${
                        isPoc 
                          ? "bg-gray-950/95 border-purple-700/40" 
                          : "bg-gray-950/90 border-gray-800"
                      }`}
                    >
                      {/* Creator Header Bar */}
                      <div className={`p-3.5 border-b flex items-center justify-between ${
                        isPoc ? "bg-purple-950/20 border-purple-800/30" : "bg-gray-900/90 border-gray-800"
                      }`}>
                        <div className="flex items-center gap-2.5">
                          <span className="w-7 h-7 rounded-full bg-purple-900/60 text-purple-200 border border-purple-700/50 flex items-center justify-center text-xs font-bold">
                            {creator.name.charAt(0).toUpperCase()}
                          </span>
                          <div>
                            <div className="text-white font-bold text-sm flex items-center gap-2">
                              <span>{creator.name}</span>
                              {isPoc && (
                                <span className="bg-purple-950 text-purple-300 text-[10px] font-bold px-2 py-0.5 rounded-md border border-purple-700/60 uppercase tracking-wide">
                                  POC
                                </span>
                              )}
                            </div>
                            <div className="text-[11px] text-gray-400 flex items-center gap-2 mt-0.5">
                              <span className="flex items-center gap-1 text-red-300">
                                <YoutubeIcon size={11} className="text-red-500" /> {ytCount} YouTube
                              </span>
                              <span>•</span>
                              <span className="flex items-center gap-1 text-pink-300">
                                <InstagramIcon size={11} className="text-pink-400" /> {igCount} Instagram
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => setActiveCreatorId(isExpanded ? null : (creator.id || creator.name))}
                            className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors flex items-center gap-1 ${
                              isPoc 
                                ? "bg-amber-950/60 hover:bg-amber-900/80 text-amber-200 border-amber-700/50" 
                                : "bg-purple-950/60 hover:bg-purple-900/80 text-purple-300 border-purple-800/50"
                            }`}
                          >
                            <Plus size={13} />
                            {isExpanded ? "Close" : "+ Add Channels"}
                            {isExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                          </button>
                          {creator.id && !isPoc && (
                            <button
                              onClick={() => {
                                if (confirm(`Remove creator "${creator.name}" and all their assigned channels?`)) {
                                  deleteCreatorMutation.mutate(creator.id!);
                                }
                              }}
                              disabled={deleteCreatorMutation.isPending}
                              className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-red-950/30 rounded-lg transition-colors"
                              title="Delete Creator"
                            >
                              <Trash2 size={15} />
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Attached Channels List under Creator */}
                      <div className="p-3">
                        {creator.channels.length === 0 ? (
                          <div className="py-3 text-center text-gray-600 text-xs italic">
                            No channels attached to {creator.name} yet. Click "+ Add Channels" above.
                          </div>
                        ) : (
                          <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {creator.channels.map((ch) => {
                              const isYT = (ch.platform || "INSTAGRAM").toUpperCase() === "YOUTUBE";
                              return (
                                <li
                                  key={ch.id}
                                  className="flex items-center justify-between p-2 bg-gray-900/60 border border-gray-800 rounded-lg text-xs hover:border-gray-700 transition-colors"
                                >
                                  <div className="flex items-center gap-2 overflow-hidden">
                                    {isYT ? (
                                      <div className="w-5 h-5 rounded-full bg-red-600 flex items-center justify-center flex-shrink-0 shadow-sm shadow-red-900/40">
                                        <YoutubeIcon size={11} className="text-white" />
                                      </div>
                                    ) : (
                                      <div className="w-5 h-5 rounded-full bg-gradient-to-tr from-yellow-400 via-pink-500 to-purple-600 flex items-center justify-center flex-shrink-0">
                                        <InstagramIcon size={11} className="text-white" />
                                      </div>
                                    )}
                                    <span className="text-gray-200 font-medium truncate" title={isYT ? (ch.channel_title || ch.username) : `@${ch.username}`}>
                                      {isYT ? (ch.channel_title || ch.username) : `@${ch.username}`}
                                    </span>
                                  </div>
                                  <button
                                    onClick={() => removeChannelMutation.mutate(ch.id)}
                                    disabled={removeChannelMutation.isPending}
                                    className="p-1 text-gray-500 hover:text-red-400 transition-colors ml-1.5"
                                    title="Remove channel"
                                  >
                                    <Trash2 size={13} />
                                  </button>
                                </li>
                              );
                            })}
                          </ul>
                        )}

                        {/* Inline Expandable Channel Picker for this Creator */}
                        {isExpanded && (
                          <div className="mt-3 pt-3 border-t border-gray-800 bg-gray-900/80 rounded-xl p-3 space-y-3">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-semibold text-white">
                                Attach Channels to <span className="text-purple-300 font-bold">{creator.name}</span>
                              </span>
                              {/* Platform Switcher */}
                              <div className="flex items-center gap-1.5">
                                <button
                                  type="button"
                                  onClick={() => setPlatform("INSTAGRAM")}
                                  className={`py-1 px-2.5 rounded-lg text-xs font-semibold flex items-center gap-1 transition-all ${
                                    platform === "INSTAGRAM"
                                      ? "bg-gradient-to-r from-pink-600/30 to-purple-600/30 border border-pink-500/50 text-pink-200"
                                      : "bg-gray-950 text-gray-400 hover:text-white border border-gray-800"
                                  }`}
                                >
                                  <InstagramIcon size={12} /> Instagram
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setPlatform("YOUTUBE")}
                                  className={`py-1 px-2.5 rounded-lg text-xs font-semibold flex items-center gap-1 transition-all ${
                                    platform === "YOUTUBE"
                                      ? "bg-red-950/50 border border-red-500/50 text-red-200"
                                      : "bg-gray-950 text-gray-400 hover:text-white border border-gray-800"
                                  }`}
                                >
                                  <YoutubeIcon size={12} className="text-red-500" /> YouTube
                                </button>
                              </div>
                            </div>

                            {/* INSTAGRAM SELECTOR */}
                            {platform === "INSTAGRAM" && (
                              <div className="space-y-2">
                                <div className="flex items-center justify-between text-[11px] text-gray-400">
                                  <span>Select Instagram Account</span>
                                </div>
                                <div className="space-y-1.5">
                                  <div className="relative flex items-center">
                                    <Search size={13} className="absolute left-2.5 text-gray-500 pointer-events-none" />
                                    <input
                                      type="text"
                                      placeholder="Search Instagram profiles by username or name..."
                                      className="w-full bg-gray-950 border border-gray-800 rounded-lg pl-8 pr-7 py-1.5 text-white text-xs placeholder-gray-500 focus:outline-none focus:border-purple-500 transition-colors"
                                      value={igSearchTerm}
                                      onChange={(e) => setIgSearchTerm(e.target.value)}
                                    />
                                    {igSearchTerm && (
                                      <button
                                        type="button"
                                        onClick={() => setIgSearchTerm("")}
                                        className="absolute right-2 text-gray-500 hover:text-gray-300 p-0.5"
                                      >
                                        <X size={12} />
                                      </button>
                                    )}
                                  </div>
                                  <select
                                    className="w-full bg-gray-950 border border-gray-700 rounded-lg p-2 text-white text-xs focus:outline-none focus:border-purple-500"
                                    value={selectedProfile}
                                    onChange={(e) => setSelectedProfile(e.target.value)}
                                    disabled={loadingProfiles}
                                  >
                                    <option value="">-- Choose Instagram profile ({filteredIgProfiles.length} available) --</option>
                                    {filteredIgProfiles.map((p) => (
                                      <option key={p.id} value={p.username}>
                                        @{p.username} {p.creator_name ? `(${p.creator_name})` : ""}
                                      </option>
                                    ))}
                                  </select>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => handleAttachChannel(creator.id, creator.name)}
                                  disabled={addChannelMutation.isPending || !selectedProfile}
                                  className="w-full py-1.5 bg-purple-700 hover:bg-purple-600 text-white font-medium rounded-lg text-xs flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
                                >
                                  <Plus size={14} />
                                  {addChannelMutation.isPending ? "Attaching..." : `Attach Instagram to ${creator.name}`}
                                </button>
                              </div>
                            )}

                            {/* YOUTUBE SELECTOR */}
                            {platform === "YOUTUBE" && (
                              <div className="space-y-2">
                                <div className="flex items-center justify-between text-[11px] text-gray-400">
                                  <span>Select YouTube Channel from Database</span>
                                </div>
                                <div className="space-y-1.5">
                                  <div className="relative flex items-center">
                                    <Search size={13} className="absolute left-2.5 text-gray-500 pointer-events-none" />
                                    <input
                                      type="text"
                                      placeholder="Search YouTube channels by title or handle..."
                                      className="w-full bg-gray-950 border border-gray-800 rounded-lg pl-8 pr-7 py-1.5 text-white text-xs placeholder-gray-500 focus:outline-none focus:border-red-500 transition-colors"
                                      value={ytSearchTerm}
                                      onChange={(e) => setYtSearchTerm(e.target.value)}
                                    />
                                    {ytSearchTerm && (
                                      <button
                                        type="button"
                                        onClick={() => setYtSearchTerm("")}
                                        className="absolute right-2 text-gray-500 hover:text-gray-300 p-0.5"
                                      >
                                        <X size={12} />
                                      </button>
                                    )}
                                  </div>
                                  <select
                                    className="w-full bg-gray-950 border border-gray-700 rounded-lg p-2 text-white text-xs focus:outline-none focus:border-red-500"
                                    value={selectedYtChannel}
                                    onChange={(e) => setSelectedYtChannel(e.target.value)}
                                    disabled={loadingYtChannels}
                                  >
                                    <option value="">-- Choose YouTube channel ({filteredYtChannels.length} available) --</option>
                                    {filteredYtChannels.map((c) => (
                                      <option key={c.id} value={c.youtube_channel_id || c.id}>
                                        ▶️ {c.title} {c.custom_url ? `(${c.custom_url})` : ""} {c.current_subscribers ? `• ${c.current_subscribers.toLocaleString()} subs` : ""}
                                      </option>
                                    ))}
                                  </select>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => handleAttachChannel(creator.id, creator.name)}
                                  disabled={addChannelMutation.isPending || !selectedYtChannel}
                                  className="w-full py-1.5 bg-red-700 hover:bg-red-600 text-white font-medium rounded-lg text-xs flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
                                >
                                  <Plus size={14} />
                                  {addChannelMutation.isPending ? "Attaching..." : `Attach YouTube to ${creator.name}`}
                                </button>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="mt-4 pt-3 border-t border-gray-800 flex items-center justify-between flex-shrink-0">
          <div className="text-xs text-gray-400">
            {isCalculating ? (
              <span className="text-purple-400 flex items-center gap-1.5 animate-pulse">
                <span className="w-2 h-2 rounded-full bg-purple-400 animate-ping" />
                Calculating and syncing metrics for YouTube & Instagram...
              </span>
            ) : (
              <span>Click "Done" to save channels and update all performance metrics.</span>
            )}
          </div>
          <button
            type="button"
            disabled={isCalculating}
            onClick={handleDone}
            className="px-6 py-2 bg-gradient-to-r from-purple-700 to-indigo-600 hover:from-purple-600 hover:to-indigo-500 text-white text-sm rounded-xl transition-all font-semibold shadow-md shadow-purple-950 flex items-center gap-2 disabled:opacity-50"
          >
            {isCalculating ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Calculating Metrics...</span>
              </>
            ) : (
              <span>Done & Update Metrics</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
