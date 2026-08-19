import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, X } from "lucide-react";
import { addChannel, removeChannel, fetchAvailableProfiles, type MicroUnit } from "../../api/microUnits";

interface ManageChannelsModalProps {
  unit: MicroUnit;
  onClose: () => void;
}

export default function ManageChannelsModal({ unit, onClose }: ManageChannelsModalProps) {
  const [usernameInput, setUsernameInput] = useState("");
  const [creatorNameInput, setCreatorNameInput] = useState("");
  const [selectedProfile, setSelectedProfile] = useState("");
  const [isCustomMode, setIsCustomMode] = useState(false);

  const queryClient = useQueryClient();

  const { data: availableProfiles = [], isLoading: loadingProfiles } = useQuery({
    queryKey: ["availableProfiles"],
    queryFn: fetchAvailableProfiles,
  });

  const addMutation = useMutation({
    mutationFn: (body: { username: string; instagram_id?: string; creator_name?: string }) =>
      addChannel(unit.id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["microUnits"] });
      setUsernameInput("");
      setCreatorNameInput("");
      setSelectedProfile("");
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
    if (isCustomMode) {
      if (!usernameInput.trim()) return;
      addMutation.mutate({
        username: usernameInput.trim(),
        creator_name: creatorNameInput.trim() || undefined,
      });
    } else {
      if (!selectedProfile) return;
      const prof = availableProfiles.find(p => p.username === selectedProfile);
      if (prof) {
        addMutation.mutate({
          username: prof.username,
          instagram_id: prof.id,
          creator_name: prof.creator_name,
        });
      }
    }
  };

  // Filter out channels already added to this unit from the dropdown list
  const existingUsernames = new Set(unit.channels.map(c => c.username.toLowerCase()));
  const unassignedProfiles = availableProfiles.filter(p => !existingUsernames.has(p.username.toLowerCase()));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-lg shadow-2xl my-auto">
        <div className="flex justify-between items-center mb-5 pb-3 border-b border-gray-800">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <span>Manage Channels</span>
              <span className="bg-purple-950 text-purple-300 text-xs px-2.5 py-0.5 rounded-full border border-purple-800">
                {unit.name}
              </span>
            </h2>
            <p className="text-xs text-gray-400 mt-1">
              Add or remove Instagram channels for this micro unit (max 5 recommended)
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
        <div className="mb-6">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2.5">
            Current Channels ({unit.channels.length})
          </h3>
          {unit.channels.length === 0 ? (
            <div className="p-4 bg-gray-950/60 rounded-xl border border-dashed border-gray-800 text-center text-gray-500 text-sm">
              No channels added to this micro unit yet.
            </div>
          ) : (
            <ul className="space-y-2 max-h-48 overflow-y-auto pr-1">
              {unit.channels.map((channel) => (
                <li
                  key={channel.id}
                  className="flex items-center justify-between p-2.5 bg-gray-800/70 border border-gray-700/60 rounded-xl text-sm hover:border-gray-600 transition-colors"
                >
                  <div className="flex items-center gap-2.5 overflow-hidden">
                    <div className="w-6 h-6 rounded-full bg-gradient-to-tr from-yellow-400 via-pink-500 to-purple-600 flex items-center justify-center flex-shrink-0">
                      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect>
                        <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path>
                        <line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line>
                      </svg>
                    </div>
                    <div className="overflow-hidden">
                      <div className="text-white font-medium truncate">@{channel.username}</div>
                      {channel.creator_name && (
                        <div className="text-xs text-gray-400 truncate">{channel.creator_name}</div>
                      )}
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
              ))}
            </ul>
          )}
        </div>

        {/* Add Channel Section */}
        <div className="pt-4 border-t border-gray-800">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              Add New Channel
            </h3>
            <button
              type="button"
              onClick={() => setIsCustomMode(!isCustomMode)}
              className="text-xs text-purple-400 hover:text-purple-300 transition-colors"
            >
              {isCustomMode ? "← Select from Scraped Profiles" : "+ Enter Custom Handle"}
            </button>
          </div>

          <form onSubmit={handleAddSubmit} className="space-y-3">
            {!isCustomMode ? (
              <div>
                <label className="block text-gray-400 text-xs mb-1">Select Instagram Profile</label>
                <select
                  className="w-full bg-gray-950 border border-gray-700 rounded-xl p-2.5 text-white text-sm focus:outline-none focus:border-purple-500"
                  value={selectedProfile}
                  onChange={(e) => setSelectedProfile(e.target.value)}
                  disabled={loadingProfiles}
                >
                  <option value="">-- Choose from available profiles --</option>
                  {unassignedProfiles.map((p) => (
                    <option key={p.id} value={p.username}>
                      @{p.username} {p.creator_name ? `(${p.creator_name})` : ""}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="space-y-2">
                <div>
                  <label className="block text-gray-400 text-xs mb-1">Instagram Handle</label>
                  <input
                    type="text"
                    placeholder="e.g. sadhguru_sharings (without @)"
                    className="w-full bg-gray-950 border border-gray-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-purple-500"
                    value={usernameInput}
                    onChange={(e) => setUsernameInput(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="block text-gray-400 text-xs mb-1">Creator Name (Optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. Sadhguru Sharings"
                    className="w-full bg-gray-950 border border-gray-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-purple-500"
                    value={creatorNameInput}
                    onChange={(e) => setCreatorNameInput(e.target.value)}
                  />
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={addMutation.isPending || (!isCustomMode ? !selectedProfile : !usernameInput.trim())}
              className="w-full mt-2 py-2.5 bg-purple-700 hover:bg-purple-600 text-white font-medium rounded-xl text-sm flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-md shadow-purple-950"
            >
              <Plus size={16} />
              {addMutation.isPending ? "Adding..." : "Add Channel to Unit"}
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
