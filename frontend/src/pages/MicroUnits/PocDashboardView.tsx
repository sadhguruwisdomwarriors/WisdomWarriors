import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchDashboard } from "../../api/microUnits";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";

const CHART_COLORS = ['#8b5cf6', '#10b981', '#f59e0b', '#ec4899', '#06b6d4'];

const formatNumber = (num: number) => {
  if (num >= 1000000) return (num / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1).replace(/\.0$/, '') + 'K';
  return num.toString();
};

const MONTH_ABBR: Record<string, string> = {
  "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May", "06": "Jun",
  "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"
};

export default function PocDashboardView() {
  const { id } = useParams<{ id: string }>();
  const [year, setYear] = useState<number>(new Date().getFullYear());

  const { data: dashboard, isLoading, error } = useQuery({
    queryKey: ["microUnitDashboard", id, year],
    queryFn: () => fetchDashboard(parseInt(id!, 10), year),
    enabled: !!id,
  });

  if (isLoading) {
    return <div className="p-6 text-gray-400">Loading dashboard...</div>;
  }

  if (error || !dashboard) {
    return <div className="p-6 text-red-400">Error loading dashboard data.</div>;
  }

  // Process data for charts
  const { available_months, channels } = dashboard;
  const sortedMonths = [...available_months].sort();

  const getMonthAbbr = (ym: string) => MONTH_ABBR[ym.slice(5, 7)] || ym;

  const chartData = sortedMonths.map(monthStr => {
    const dataPoint: any = { month: getMonthAbbr(monthStr) };
    channels.forEach(channel => {
      if (channel.months[monthStr]) {
        dataPoint[`${channel.username}_views`] = channel.months[monthStr].views;
        dataPoint[`${channel.username}_posts`] = channel.months[monthStr].post_count;
      } else {
        dataPoint[`${channel.username}_views`] = 0;
        dataPoint[`${channel.username}_posts`] = 0;
      }
    });
    return dataPoint;
  });

  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: 5 }, (_, i) => currentYear - 2 + i);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <h1 className="text-2xl font-bold text-white">
          {dashboard.unit.name} - Performance Dashboard
        </h1>
        <div className="flex items-center gap-2">
          <label className="text-gray-400 text-sm">Year:</label>
          <select
            className="bg-gray-800 border border-gray-700 rounded p-1.5 text-white text-sm"
            value={year}
            onChange={(e) => setYear(parseInt(e.target.value, 10))}
          >
            {years.map(y => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-gray-800 text-gray-300 text-sm">
              <th className="p-4 font-semibold border-b border-gray-700 whitespace-nowrap">Channel Name</th>
              {sortedMonths.map(month => (
                <th key={month} className="p-4 font-semibold border-b border-gray-700 text-right whitespace-nowrap">
                  {getMonthAbbr(month)} {year}
                </th>
              ))}
              {sortedMonths.length === 0 && (
                <th className="p-4 font-semibold border-b border-gray-700 text-gray-500 italic">No data available for {year}</th>
              )}
            </tr>
          </thead>
          <tbody>
            {channels.map((channel) => (
              <tr key={channel.instagram_id} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors text-sm">
                <td className="p-4">
                  <a 
                    href={`https://www.instagram.com/${channel.username}/`} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-purple-400 hover:text-purple-300 font-medium"
                  >
                    @{channel.username}
                  </a>
                  {channel.creator_name && <div className="text-gray-500 text-xs mt-0.5">{channel.creator_name}</div>}
                </td>
                {sortedMonths.map(month => {
                  const mData = channel.months[month];
                  return (
                    <td key={month} className="p-4 text-right text-gray-300 whitespace-nowrap">
                      {mData ? (
                        <span>
                          <span className="font-medium">{formatNumber(mData.views)}</span>
                          <span className="text-gray-500 ml-1">({mData.post_count})</span>
                        </span>
                      ) : (
                        <span className="text-gray-600">—</span>
                      )}
                    </td>
                  );
                })}
                {sortedMonths.length === 0 && <td className="p-4"></td>}
              </tr>
            ))}
            {channels.length === 0 && (
              <tr>
                <td colSpan={sortedMonths.length + 1} className="p-6 text-center text-gray-500 italic">
                  No channels assigned to this micro unit.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {sortedMonths.length > 0 && channels.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h3 className="text-lg font-semibold text-white mb-4">Monthly Views Trend</h3>
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
                    contentStyle={{ backgroundColor: '#1f2937', borderColor: '#374151', color: '#f3f4f6' }}
                    formatter={(value: any) => formatNumber(Number(value) || 0)}
                  />
                  <Legend wrapperStyle={{ paddingTop: '10px' }} />
                  {channels.map((channel, idx) => (
                    <Line 
                      key={channel.instagram_id}
                      type="monotone" 
                      dataKey={`${channel.username}_views`} 
                      name={`@${channel.username}`}
                      stroke={CHART_COLORS[idx % CHART_COLORS.length]} 
                      strokeWidth={2}
                      dot={{ r: 4 }}
                      activeDot={{ r: 6 }}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h3 className="text-lg font-semibold text-white mb-4">Monthly Posts Count</h3>
            <div className="h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
                  <XAxis dataKey="month" stroke="#9ca3af" tick={{ fill: '#9ca3af' }} />
                  <YAxis stroke="#9ca3af" tick={{ fill: '#9ca3af' }} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#1f2937', borderColor: '#374151', color: '#f3f4f6' }}
                    cursor={{ fill: '#374151', opacity: 0.4 }}
                  />
                  <Legend wrapperStyle={{ paddingTop: '10px' }} />
                  {channels.map((channel, idx) => (
                    <Bar 
                      key={channel.instagram_id}
                      dataKey={`${channel.username}_posts`} 
                      name={`@${channel.username}`}
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
