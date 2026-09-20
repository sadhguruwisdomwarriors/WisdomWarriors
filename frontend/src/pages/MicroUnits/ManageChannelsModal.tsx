import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, X } from "lucide-react";
import { 
  addChannel, 
  removeChannel, 
  fetchAvailableProfiles, 
  fetchAvailableYoutubeChannels,
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
  const [platform, setPlatform] = useState<"INSTAGRAM" | "YOUTUBE">("INSTAGRAM");
  const [creatorNameInput, setCreatorNameInput] = useState("");
  
  // Instagram states
  const [usernameInput, setUsernameInput] = useState("");
  const [selectedProfile, setSelectedProfile] = useState("");
  const [isCustomMode, setIsCustomMode] = useState(false);

  // YouTube states
  const [selectedYtChannel, setSelectedYtChannel] = useState("");
  const [ytSearchTerm, setYtSearchTerm] = useState("");
  const [customYtId, setCustomYtId] = useState("");
  const [customYtTitle, setCustomYtTitle] = useState("");

  const queryClient = useQueryClient();

  const { data: availableProfiles = [], isLoading: loadingProfiles } = useQuery({
    queryKey: ["availableProfiles"],
    queryFn: fetchAvailableProfiles,
  });

  const { data: availableYtChannels = [], isLoading: loadingYtChannels } = useQuery({
    queryKey: ["availableYoutubeChannels"],
    queryFn: fetchAvailableYoutubeChannels,
  });

  const addMutation = useMutation({
    mutationFn: (body: { 
      platform: "INSTAGRAM" | "YOUTUBE";
      username: string; 
      instagram_id?: string; 
      creator_name?: string;
      channel_title?: string;
    }) => addChannel(unit.id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["microUnits"] });
      setUsernameInput("");
      setCreatorNameInput("");
      setSelectedProfile("");
      setSelectedYtChannel("");
      setCustomYtId("");
      setCustomYtTitle("");
    },
    onError: (err: any) => {
      alert(`Error adding channel: ${err.message}`);
    },
  });

  const removeMutation = useMutation({
    mutationFn: (channelId: number) => removeChannel(unit.id, channelId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["microUnits"] });
    },
    onError: (err: any) => {
      alert(`Error removing channel: ${err.message}`);
    },
  });

  const handleAddSubmit = (e: FormEvent) => {
    e.preventDefault();

    if (platform === "INSTAGRAM") {
      if (isCustomMode) {
        if (!usernameInput.trim()) return;
        const cleanUser = usernameInput.trim().replace(/^@/, '');
        addMutation.mutate({
          platform: "INSTAGRAM",
          username: cleanUser,
          creator_name: creatorNameInput.trim() || cleanUser,
          channel_title: `@${cleanUser}`,
        });
      } else {
        if (!selectedProfile) return;
        const prof = availableProfiles.find(p => p.username === selectedProfile);
        if (prof) {
          addMutation.mutate({
            platform: "INSTAGRAM",
            username: prof.username,
            instagram_id: prof.id,
            creator_name: creatorNameInput.trim() || prof.creator_name || `@${prof.username}`,
            channel_title: `@${prof.username}`,
          });
        }
      }
    } else {
      // YouTube
      if (isCustomMode) {
        if (!customYtId.trim()) return;
        addMutation.mutate({
          platform: "YOUTUBE",
          username: customYtId.trim(),
          creator_name: creatorNameInput.trim() || customYtTitle.trim() || customYtId.trim(),
          channel_title: customYtTitle.trim() || customYtId.trim(),
        });
      } else {
        if (!selectedYtChannel) return;
        const yt = availableYtChannels.find(c => c.youtube_channel_id === selectedYtChannel || c.id === selectedYtChannel);
        if (yt) {
          addMutation.mutate({
            platform: "YOUTUBE",
            username: yt.youtube_channel_id || yt.id,
            instagram_id: yt.youtube_channel_id || yt.id,
            creator_name: creatorNameInput.trim() || yt.title || "YouTube Creator",
            channel_title: yt.title,
          });
        }
      }
    }
  };

  // Filter out channels already added
  const existingKeys = new Set(unit.channels.map(c => `${c.platform || 'INSTAGRAM'}_${c.username.toLowerCase()}`));
  
  const unassignedProfiles = availableProfiles.filter(
    p => !existingKeys.has(`INSTAGRAM_${p.username.toLowerCase()}`)
  );

  const filteredYtChannels = availableYtChannels
    .filter(c => !existingKeys.has(`YOUTUBE_${(c.youtube_channel_id || c.id).toLowerCase()}`))
    .filter(c => !ytSearchTerm || c.title.toLowerCase().includes(ytSearchTerm.toLowerCase()) || c.custom_url.toLowerCase().includes(ytSearchTerm.toLowerCase()));

  // Extract unique creator names from existing channels for quick suggestions
  const existingCreatorNames = Array.from(
    new Set(unit.channels.map(c => c.creator_name).filter(Boolean))
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-lg shadow-2xl my-auto">
        <div className="flex justify-between items-center mb-5 pb-3 border-b border-gray-800">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <span>Edit Channels</span>
              <span className="bg-purple-950 text-purple-300 text-xs px-2.5 py-0.5 rounded-full border border-purple-800">
                {unit.name}
              </span>
            </h2>
            <p className="text-xs text-gray-400 mt-1">
              Add multiple YouTube and Instagram channels grouped by Content Creator
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Existing Channels List */}
        <div className="mb-5">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2.5">
            Current Channels ({unit.channels.length})
          </h3>
          {unit.channels.length === 0 ? (
            <div className="p-4 bg-gray-950/60 rounded-xl border border-dashed border-gray-800 text-center text-gray-500 text-sm">
              No channels added to this micro unit yet.
            </div>
          ) : (
            <ul className="space-y-2 max-h-44 overflow-y-auto pr-1">
              {unit.channels.map((channel) => {
                const isYT = (channel.platform || "INSTAGRAM").toUpperCase() === "YOUTUBE";
                return (
                  <li
                    key={channel.id}
                    className="flex items-center justify-between p-2.5 bg-gray-800/70 border border-gray-700/60 rounded-xl text-sm hover:border-gray-600 transition-colors"
                  >
                    <div className="flex items-center gap-2.5 overflow-hidden">
                      {isYT ? (
                        <div className="w-6 h-6 rounded-full bg-red-600 flex items-center justify-center flex-shrink-0 shadow-sm shadow-red-900/40">
                          <YoutubeIcon size={13} className="text-white" />
                        </div>
                      ) : (
                        <div className="w-6 h-6 rounded-full bg-gradient-to-tr from-yellow-400 via-pink-500 to-purple-600 flex items-center justify-center flex-shrink-0">
                          <InstagramIcon size={13} className="text-white" />
                        </div>
                      )}
                      <div className="overflow-hidden">
                        <div className="text-white font-medium truncate">
                          {isYT ? (channel.channel_title || channel.username) : `@${channel.username}`}
                        </div>
                        <div className="text-xs text-purple-300 font-medium truncate">
                          Creator: {channel.creator_name || "Unassigned"}
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => removeMutation.mutate(channel.id)}
                      disabled={removeMutation.isPending}
                      className="p-1.5 text-gray-400 hover:text-red-400 hover:bg-red-950/40 rounded-lg transition-colors ml-2"
                      title="Remove channel"
                    >
                      <Trash2 size={15} />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Add Channel Section */}
        <div className="pt-4 border-t border-gray-800">
          {/* Platform Tabs */}
          <div className="flex items-center gap-2 mb-3">
            <button
              type="button"
              onClick={() => setPlatform("INSTAGRAM")}
              className={`flex-1 py-1.5 px-3 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 border transition-all ${
                platform === "INSTAGRAM"
                  ? "bg-gradient-to-r from-pink-600/30 to-purple-600/30 border-pink-500/50 text-pink-200"
                  : "bg-gray-950 border-gray-800 text-gray-400 hover:text-white"
              }`}
            >
              <InstagramIcon size={14} />
              Instagram Channel
            </button>
            <button
              type="button"
              onClick={() => setPlatform("YOUTUBE")}
              className={`flex-1 py-1.5 px-3 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 border transition-all ${
                platform === "YOUTUBE"
                  ? "bg-red-950/50 border-red-500/50 text-red-200"
                  : "bg-gray-950 border-gray-800 text-gray-400 hover:text-white"
              }`}
            >
              <YoutubeIcon size={14} className="text-red-500" />
              YouTube Channel
            </button>
          </div>

          <form onSubmit={handleAddSubmit} className="space-y-3">
            {/* Creator Name Field */}
            <div>
              <label className="block text-gray-300 text-xs font-medium mb-1">
                Content Creator Name
              </label>
              <input
                type="text"
                placeholder="e.g. Sanjeev Yogii, Priya Sharma"
                list="creator-names-list"
                className="w-full bg-gray-950 border border-gray-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-purple-500 placeholder-gray-600"
                value={creatorNameInput}
                onChange={(e) => setCreatorNameInput(e.target.value)}
              />
              <datalist id="creator-names-list">
                {existingCreatorNames.map((name, i) => (
                  <option key={i} value={name} />
                ))}
              </datalist>
            </div>

            {/* INSTAGRAM FORM */}
            {platform === "INSTAGRAM" && (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-400">Instagram Account</span>
                  <button
                    type="button"
                    onClick={() => setIsCustomMode(!isCustomMode)}
                    className="text-xs text-purple-400 hover:text-purple-300 transition-colors"
                  >
                    {isCustomMode ? "← Select from Scraped Profiles" : "+ Enter Custom Handle"}
                  </button>
                </div>

                {!isCustomMode ? (
                  <div>
                    <select
                      className="w-full bg-gray-950 border border-gray-700 rounded-xl p-2.5 text-white text-sm focus:outline-none focus:border-purple-500"
                      value={selectedProfile}
                      onChange={(e) => {
                        setSelectedProfile(e.target.value);
                        if (!creatorNameInput) {
                          const prof = availableProfiles.find(p => p.username === e.target.value);
                          if (prof?.creator_name) setCreatorNameInput(prof.creator_name);
                        }
                      }}
                      disabled={loadingProfiles}
                    >
                      <option value="">-- Choose Instagram profile --</option>
                      {unassignedProfiles.map((p) => (
                        <option key={p.id} value={p.username}>
                          @{p.username} {p.creator_name ? `(${p.creator_name})` : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <div>
                    <input
                      type="text"
                      placeholder="e.g. sanjeev_yogii (without @)"
                      className="w-full bg-gray-950 border border-gray-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-purple-500"
                      value={usernameInput}
                      onChange={(e) => setUsernameInput(e.target.value)}
                      required
                    />
                  </div>
                )}
              </>
            )}

            {/* YOUTUBE FORM */}
            {platform === "YOUTUBE" && (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-400">YouTube Channel from Database</span>
                  <button
                    type="button"
                    onClick={() => setIsCustomMode(!isCustomMode)}
                    className="text-xs text-red-400 hover:text-red-300 transition-colors"
                  >
                    {isCustomMode ? "← Select from YouTube DB" : "+ Enter Custom Channel ID"}
                  </button>
                </div>

                {!isCustomMode ? (
                  <div className="space-y-2">
                    {availableYtChannels.length > 8 && (
                      <input
                        type="text"
                        placeholder="Search YouTube channel by title..."
                        className="w-full bg-gray-950 border border-gray-800 rounded-xl px-3 py-1.5 text-white text-xs placeholder-gray-600 focus:outline-none focus:border-red-500"
                        value={ytSearchTerm}
                        onChange={(e) => setYtSearchTerm(e.target.value)}
                      />
                    )}
                    <select
                      className="w-full bg-gray-950 border border-gray-700 rounded-xl p-2.5 text-white text-sm focus:outline-none focus:border-red-500"
                      value={selectedYtChannel}
                      onChange={(e) => {
                        setSelectedYtChannel(e.target.value);
                        if (!creatorNameInput) {
                          const yt = availableYtChannels.find(c => c.youtube_channel_id === e.target.value || c.id === e.target.value);
                          if (yt?.title) setCreatorNameInput(yt.title);
                        }
                      }}
                      disabled={loadingYtChannels}
                    >
                      <option value="">-- Choose YouTube channel --</option>
                      {filteredYtChannels.map((c) => (
                        <option key={c.id} value={c.youtube_channel_id || c.id}>
                          ▶️ {c.title} {c.custom_url ? `(${c.custom_url})` : ""} {c.current_subscribers ? `• ${c.current_subscribers.toLocaleString()} subs` : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div>
                      <label className="block text-gray-400 text-xs mb-1">YouTube Channel ID / Handle</label>
                      <input
                        type="text"
                        placeholder="e.g. UC_xxxx or @ChannelHandle"
                        className="w-full bg-gray-950 border border-gray-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-red-500"
                        value={customYtId}
                        onChange={(e) => setCustomYtId(e.target.value)}
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-gray-400 text-xs mb-1">Channel Display Title</label>
                      <input
                        type="text"
                        placeholder="e.g. Sanjeev Wisdom Warriors"
                        className="w-full bg-gray-950 border border-gray-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-red-500"
                        value={customYtTitle}
                        onChange={(e) => setCustomYtTitle(e.target.value)}
                      />
                    </div>
                  </div>
                )}
              </>
            )}

            <button
              type="submit"
              disabled={
                addMutation.isPending || 
                (platform === "INSTAGRAM" 
                  ? (!isCustomMode ? !selectedProfile : !usernameInput.trim())
                  : (!isCustomMode ? !selectedYtChannel : !customYtId.trim()))
              }
              className={`w-full mt-3 py-2.5 text-white font-medium rounded-xl text-sm flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-md ${
                platform === "YOUTUBE"
                  ? "bg-red-700 hover:bg-red-600 shadow-red-950"
                  : "bg-purple-700 hover:bg-purple-600 shadow-purple-950"
              }`}
            >
              <Plus size={16} />
              {addMutation.isPending ? "Adding..." : `Add ${platform === "YOUTUBE" ? "YouTube" : "Instagram"} Channel`}
            </button>
          </form>
        </div>

        <div className="mt-6 pt-4 border-t border-gray-800 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2 bg-gray-800 hover:bg-gray-700 text-white text-sm rounded-xl transition-colors font-medium"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
