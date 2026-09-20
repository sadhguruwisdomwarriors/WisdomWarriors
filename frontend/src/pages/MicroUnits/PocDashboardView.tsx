import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchDashboard } from "../../api/microUnits";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { Award, Video, Film } from "lucide-react";

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

const CHART_COLORS = ['#8b5cf6', '#ef4444', '#10b981', '#f59e0b', '#ec4899', '#06b6d4'];

const formatNumber = (num: number) => {
  if (num >= 1000000) return (num / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1).replace(/\.0$/, '') + 'K';
  return Math.round(num).toLocaleString();
};

const MONTH_ABBR: Record<string, string> = {
  "01": "January", "02": "February", "03": "March", "04": "April", "05": "May", "06": "June",
  "07": "July", "08": "August", "09": "September", "10": "October", "11": "November", "12": "December"
};

export default function PocDashboardView({ unitIdOverride }: { unitIdOverride?: number } = {}) {
  const { id } = useParams<{ id: string }>();
  const activeUnitId = unitIdOverride || (id ? parseInt(id, 10) : undefined);
  const [year, setYear] = useState<number>(new Date().getFullYear());

  const { data: dashboard, isLoading, error } = useQuery({
    queryKey: ["microUnitDashboard", activeUnitId, year],
    queryFn: () => fetchDashboard(activeUnitId!, year),
    enabled: !!activeUnitId,
  });

  if (isLoading) {
    return <div className="p-8 text-center text-gray-400">Loading performance dashboard...</div>;
  }

  if (error || !dashboard) {
    return <div className="p-8 text-center text-red-400">Error loading dashboard data.</div>;
  }

  const { available_months, creators = [], unit_totals = {} } = dashboard;
  const sortedMonths = [...available_months].sort();

  const getMonthName = (ym: string) => {
    const m = ym.slice(5, 7);
    return `${MONTH_ABBR[m] || ym} ${ym.slice(0, 4)}`;
  };

  function ymShort(ym: string) {
    const m = ym.slice(5, 7);
    const shortNames: Record<string, string> = {
      "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May", "06": "Jun",
      "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"
    };
    return shortNames[m] || ym;
  }

  // Build Chart Data per Creator
  const chartData = sortedMonths.map(monthStr => {
    const dataPoint: any = { month: ymShort(monthStr) };
    creators.forEach(creator => {
      const mData = creator.months?.[monthStr];
      dataPoint[`${creator.creator_name}_views`] = mData ? mData.total_views : 0;
      dataPoint[`${creator.creator_name}_uploads`] = mData ? (mData.videos + mData.reels) : 0;
    });
    return dataPoint;
  });

  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: 5 }, (_, i) => currentYear - 2 + i);

  // Latest active month for top banner summary
  const latestMonth = sortedMonths[sortedMonths.length - 1];
  const latestTotals = latestMonth ? unit_totals[latestMonth] : null;

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <span>{dashboard.unit.name}</span>
            <span className="text-gray-400 font-normal text-lg">Performance Dashboard</span>
          </h1>
          {dashboard.unit.poc && (
            <p className="text-xs text-gray-400 mt-0.5">
              POC: <span className="text-purple-300 font-semibold">{dashboard.unit.poc}</span>
            </p>
          )}
        </div>

        <div className="flex items-center gap-2">
          <label className="text-gray-400 text-sm">Year:</label>
          <select
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:border-purple-500"
            value={year}
            onChange={(e) => setYear(parseInt(e.target.value, 10))}
          >
            {years.map(y => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Unit Level KPI Summary Cards for latest calculated month */}
      {latestTotals && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-gradient-to-br from-purple-950/60 to-gray-900 border border-purple-800/40 rounded-2xl p-4 shadow-lg">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-purple-300 uppercase tracking-wider">
                Unit Total Views ({getMonthName(latestMonth)})
              </span>
              <Award className="text-purple-400" size={18} />
            </div>
            <div className="text-2xl font-extrabold text-white mt-1">
              {formatNumber(latestTotals.total_views)}
            </div>
            <div className="text-xs text-gray-400 mt-1">
              Combined YouTube & Instagram reach
            </div>
          </div>

          <div className="bg-gradient-to-br from-red-950/40 to-gray-900 border border-red-900/40 rounded-2xl p-4 shadow-lg">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-red-300 uppercase tracking-wider flex items-center gap-1.5">
                <YoutubeIcon size={14} className="text-red-500" /> YouTube Views
              </span>
              <Video className="text-red-400" size={18} />
            </div>
            <div className="text-2xl font-extrabold text-white mt-1">
              {formatNumber(latestTotals.yt_views)}
            </div>
            <div className="text-xs text-gray-400 mt-1">
              {latestTotals.videos} videos uploaded
            </div>
          </div>

          <div className="bg-gradient-to-br from-pink-950/40 to-gray-900 border border-pink-900/40 rounded-2xl p-4 shadow-lg">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-pink-300 uppercase tracking-wider flex items-center gap-1.5">
                <InstagramIcon size={14} className="text-pink-400" /> Instagram Views
              </span>
              <Film className="text-pink-400" size={18} />
            </div>
            <div className="text-2xl font-extrabold text-white mt-1">
              {formatNumber(latestTotals.ig_views)}
            </div>
            <div className="text-xs text-gray-400 mt-1">
              {latestTotals.reels} reels credited
            </div>
          </div>
        </div>
      )}

      {/* Main Multi-Column Spreadsheet Table */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-x-auto shadow-xl">
        <table className="w-full text-left border-collapse min-w-[700px]">
          <thead>
            <tr className="bg-gray-800/90 text-gray-300 text-sm border-b border-gray-700">
              <th className="p-4 font-semibold w-56 border-r border-gray-700/60 whitespace-nowrap">
                Content Creator
              </th>
              {sortedMonths.map(month => (
                <th key={month} className="p-4 font-semibold text-center border-r border-gray-700/60 whitespace-nowrap min-w-[420px]">
                  {getMonthName(month)}
                </th>
              ))}
              {sortedMonths.length === 0 && (
                <th className="p-4 font-semibold text-gray-500 italic text-center">
                  No monthly calculations found for {year}. Click "Calculate Monthly Metrics" to generate.
                </th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {creators.map((creator, cIdx) => (
              <tr key={cIdx} className="hover:bg-gray-850/40 transition-colors">
                {/* Left Column: Creator Profile / Name */}
                <td className="p-4 align-top border-r border-gray-800 bg-gray-900/60">
                  <div className="space-y-1">
                    <div className="text-white font-bold text-base flex items-center gap-2">
                      <span className="w-7 h-7 rounded-full bg-purple-900/60 text-purple-200 border border-purple-700/50 flex items-center justify-center text-xs font-bold">
                        {creator.creator_name.charAt(0).toUpperCase()}
                      </span>
                      <span className="truncate" title={creator.creator_name}>
                        {creator.creator_name}
                      </span>
                    </div>
                    <div className="text-xs text-gray-400 pl-9">
                      {creator.channels_count} {creator.channels_count === 1 ? "Channel" : "Channels"}
                    </div>
                  </div>
                </td>

                {/* Monthly Columns (Spreadsheet 2-Column Split Box) */}
                {sortedMonths.map(month => {
                  const mData = creator.months?.[month];
                  const hasData = mData && (mData.yt_channels?.length > 0 || mData.ig_channels?.length > 0);

                  return (
                    <td key={month} className="p-3 align-top border-r border-gray-800">
                      {hasData ? (
                        <div className="bg-gray-950/80 border border-gray-800 rounded-xl overflow-hidden shadow-sm">
                          {/* 2-Column Grid: YouTube on Left | Instagram on Right */}
                          <div className="grid grid-cols-2 divide-x divide-gray-800 p-3 gap-3">
                            {/* YouTube Channels Sub-Column */}
                            <div className="space-y-2.5">
                              <div className="text-[11px] font-bold text-red-400 uppercase tracking-wider flex items-center gap-1">
                                <YoutubeIcon size={13} className="text-red-500 flex-shrink-0" />
                                <span>YouTube</span>
                              </div>
                              {mData.yt_channels && mData.yt_channels.length > 0 ? (
                                <div className="space-y-2">
                                  {mData.yt_channels.map((yt, idx) => (
                                    <div key={idx} className="bg-gray-900/80 border border-gray-800/80 rounded-lg p-2 text-xs space-y-0.5">
                                      <div className="font-semibold text-gray-200 truncate" title={yt.title}>
                                        {yt.title}
                                      </div>
                                      <div className="text-white font-medium">
                                        Views - <span className="text-white font-bold">{formatNumber(yt.views)}</span>
                                      </div>
                                      <div className="text-red-300/90 font-medium">
                                        Videos - <span className="font-semibold">{yt.videos}</span>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <div className="text-gray-600 text-xs italic py-2">
                                  No YT channels
                                </div>
                              )}
                            </div>

                            {/* Instagram Channels Sub-Column */}
                            <div className="space-y-2.5 pl-3">
                              <div className="text-[11px] font-bold text-pink-400 uppercase tracking-wider flex items-center gap-1">
                                <InstagramIcon size={13} className="text-pink-400 flex-shrink-0" />
                                <span>Instagram</span>
                              </div>
                              {mData.ig_channels && mData.ig_channels.length > 0 ? (
                                <div className="space-y-2">
                                  {mData.ig_channels.map((ig, idx) => (
                                    <div key={idx} className="bg-gray-900/80 border border-gray-800/80 rounded-lg p-2 text-xs space-y-0.5">
                                      <div className="font-semibold text-purple-300 truncate" title={`@${ig.username}`}>
                                        @{ig.username}
                                      </div>
                                      <div className="text-white font-medium">
                                        Views - <span className="text-white font-bold">{formatNumber(ig.views)}</span>
                                      </div>
                                      <div className="text-pink-300/90 font-medium">
                                        Reels - <span className="font-semibold">{ig.reels}</span>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <div className="text-gray-600 text-xs italic py-2">
                                  No IG channels
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Bottom Highlighted Total Views for Creator */}
                          <div className="bg-gray-900 border-t border-gray-800 px-3 py-2 flex items-center justify-between text-xs">
                            <span className="font-semibold text-gray-400 uppercase tracking-wider text-[11px]">
                              Total Views
                            </span>
                            <span className="font-bold text-white text-sm bg-purple-950/70 border border-purple-800/50 px-2 py-0.5 rounded-md shadow-sm">
                              {formatNumber(mData.total_views)}
                            </span>
                          </div>
                        </div>
                      ) : (
                        <div className="text-center text-gray-600 italic py-6 text-xs">
                          —
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}

            {creators.length === 0 && (
              <tr>
                <td colSpan={sortedMonths.length + 1} className="p-8 text-center text-gray-500 italic">
                  No creators or channels configured in this micro unit yet.
                </td>
              </tr>
            )}
          </tbody>

          {/* Unit Total Views Table Footer */}
          {sortedMonths.length > 0 && creators.length > 0 && (
            <tfoot>
              <tr className="bg-gray-800/95 border-t-2 border-purple-800/60 font-bold text-sm">
                <td className="p-4 text-white border-r border-gray-700 uppercase tracking-wider text-xs">
                  Micro Unit Total
                </td>
                {sortedMonths.map(month => {
                  const totals = unit_totals[month] || { total_views: 0, yt_views: 0, ig_views: 0 };
                  return (
                    <td key={month} className="p-4 text-center border-r border-gray-700">
                      <div className="inline-flex flex-col items-center gap-0.5">
                        <span className="text-base text-purple-300 font-extrabold">
                          {formatNumber(totals.total_views)} Total Views
                        </span>
                        <div className="flex items-center gap-2 text-[11px] text-gray-400 font-normal">
                          <span className="text-red-400">YT: {formatNumber(totals.yt_views)}</span>
                          <span>•</span>
                          <span className="text-pink-400">IG: {formatNumber(totals.ig_views)}</span>
                        </div>
                      </div>
                    </td>
                  );
                })}
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {/* Monthly Trends Analytics Charts */}
      {sortedMonths.length > 0 && creators.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-2">
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 shadow-lg">
            <h3 className="text-base font-bold text-white mb-4 flex items-center gap-2">
              <span>Creator Monthly Views Trend</span>
            </h3>
            <div className="h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
                  <XAxis dataKey="month" stroke="#9ca3af" tick={{ fill: '#9ca3af' }} />
                  <YAxis 
                    stroke="#9ca3af" 
                    tick={{ fill: '#9ca3af' }} 
                    tickFormatter={(value) => formatNumber(value)}
                  />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#1f2937', borderColor: '#374151', color: '#f3f4f6', borderRadius: '0.75rem' }}
                    formatter={(value: any) => [formatNumber(Number(value) || 0), "Views"]}
                  />
                  <Legend wrapperStyle={{ paddingTop: '10px' }} />
                  {creators.map((creator, idx) => (
                    <Line 
                      key={idx}
                      type="monotone" 
                      dataKey={`${creator.creator_name}_views`} 
                      name={creator.creator_name}
                      stroke={CHART_COLORS[idx % CHART_COLORS.length]} 
                      strokeWidth={2.5}
                      dot={{ r: 4 }}
                      activeDot={{ r: 6 }}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 shadow-lg">
            <h3 className="text-base font-bold text-white mb-4 flex items-center gap-2">
              <span>Creator Monthly Uploads (Videos & Reels)</span>
            </h3>
            <div className="h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
                  <XAxis dataKey="month" stroke="#9ca3af" tick={{ fill: '#9ca3af' }} />
                  <YAxis stroke="#9ca3af" tick={{ fill: '#9ca3af' }} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#1f2937', borderColor: '#374151', color: '#f3f4f6', borderRadius: '0.75rem' }}
                    cursor={{ fill: '#374151', opacity: 0.4 }}
                  />
                  <Legend wrapperStyle={{ paddingTop: '10px' }} />
                  {creators.map((creator, idx) => (
                    <Bar 
                      key={idx}
                      dataKey={`${creator.creator_name}_uploads`} 
                      name={creator.creator_name}
                      fill={CHART_COLORS[idx % CHART_COLORS.length]} 
                      radius={[4, 4, 0, 0]}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
