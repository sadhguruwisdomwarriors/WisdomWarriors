import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { API_URL } from "../../config";
import { authHeaders } from "../../api/auth";
import { X, Search } from "lucide-react";

interface InspectRunModalProps {
  onClose: () => void;
}

export default function InspectRunModal({ onClose }: InspectRunModalProps) {
  const [selectedChannel, setSelectedChannel] = useState<string>("bhoomija.yogini");

  const { data, isLoading, error } = useQuery({
    queryKey: ["inspectRun97"],
    queryFn: async () => {
      const res = await fetch(`${API_URL}/api/micro-units/inspect-run-97`, {
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error("Failed to fetch inspection data");
      return res.json();
    },
  });

  const channels = ["bhoomija.yogini", "_rudreshi_", "_when.the.guru.invades_"];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-3xl shadow-2xl my-auto">
        <div className="flex justify-between items-center mb-5 pb-3 border-b border-gray-800">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Search size={20} className="text-purple-400" />
              <span>Database Inspection — Run #97</span>
            </h2>
            <p className="text-xs text-gray-400 mt-1">
              Live database post breakdown and view counts for Micro Unit 1 channels
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Channel selector tabs */}
        <div className="flex gap-2 mb-6 border-b border-gray-800 pb-3">
          {channels.map((ch) => (
            <button
              key={ch}
              onClick={() => setSelectedChannel(ch)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                selectedChannel === ch
                  ? "bg-purple-700 text-white shadow-md shadow-purple-900/40"
                  : "bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700"
              }`}
            >
              @{ch}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="py-12 text-center text-gray-400 flex flex-col items-center gap-3">
            <div className="w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
            <span>Fetching Run 97 post records from database...</span>
          </div>
        ) : error ? (
          <div className="p-4 bg-red-950/50 border border-red-800 text-red-300 rounded-xl text-sm">
            Error loading data: {(error as any).message}
          </div>
        ) : data ? (
          <div className="space-y-6">
            {(() => {
              const chData = data[selectedChannel];
              if (!chData) {
                return <div className="text-gray-500 text-sm">No data found for this channel in Run 97.</div>;
              }

              const months = Object.keys(chData.by_month || {}).sort();

              return (
                <div>
                  <div className="flex items-center justify-between bg-gray-950/80 p-3.5 rounded-xl border border-gray-800 mb-4">
                    <div>
                      <span className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Total Posts in Run 97:</span>{" "}
                      <span className="text-purple-300 font-bold text-base ml-1">{chData.total_posts_in_run_97}</span>
                    </div>
                    <div>
                      <span className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Months with Data:</span>{" "}
                      <span className="text-white font-bold text-base ml-1">{months.length}</span>
                    </div>
                  </div>

                  <div className="overflow-x-auto rounded-xl border border-gray-800">
                    <table className="w-full text-left text-sm">
                      <thead className="bg-gray-800/80 text-gray-400 text-xs uppercase">
                        <tr>
                          <th className="px-4 py-3">Month</th>
                          <th className="px-4 py-3">Post Count</th>
                          <th className="px-4 py-3">Total Views</th>
                          <th className="px-4 py-3">Avg Views / Post</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-800 bg-gray-900">
                        {months.length === 0 ? (
                          <tr>
                            <td colSpan={4} className="px-4 py-4 text-center text-gray-500">
                              No posts found for this channel in Run 97.
                            </td>
                          </tr>
                        ) : (
                          months.map((m: string) => {
                            const mInfo = chData.by_month[m];
                            const avgViews = mInfo.post_count > 0 ? Math.round(mInfo.total_views / mInfo.post_count) : 0;
                            return (
                              <tr key={m} className="hover:bg-gray-800/50 transition-colors">
                                <td className="px-4 py-3 font-semibold text-white">{m}</td>
                                <td className="px-4 py-3 text-purple-300 font-medium">{mInfo.post_count} posts</td>
                                <td className="px-4 py-3 text-emerald-400 font-bold">{mInfo.total_views.toLocaleString()} views</td>
                                <td className="px-4 py-3 text-gray-300">{avgViews.toLocaleString()}</td>
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })()}
          </div>
        ) : null}

        <div className="mt-6 pt-4 border-t border-gray-800 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2 bg-gray-800 hover:bg-gray-700 text-white text-sm rounded-xl transition-colors font-medium"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
