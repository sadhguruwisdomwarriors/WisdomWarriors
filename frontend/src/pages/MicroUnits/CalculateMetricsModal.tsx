import { useState, useMemo, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchScrapeRuns, calculateMonthlyMetrics, type MonthEntry } from "../../api/microUnits";
import { format } from "date-fns";

interface CalculateMetricsModalProps {
  onClose: () => void;
}

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

export default function CalculateMetricsModal({ onClose }: CalculateMetricsModalProps) {
  const [year, setYear] = useState<number>(new Date().getFullYear());
  const [monthEntries, setMonthEntries] = useState<Record<number, { s1: string; s2: string }>>({});
  const queryClient = useQueryClient();

  const { data: scrapeRuns = [], isLoading: loadingRuns } = useQuery({
    queryKey: ["scrapeRuns"],
    queryFn: fetchScrapeRuns,
  });

  const calcMutation = useMutation({
    mutationFn: calculateMonthlyMetrics,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["microUnits"] });
      alert("Metrics calculated successfully!");
      onClose();
    },
    onError: (err: any) => {
      alert(`Error calculating metrics: ${err.message}`);
    },
  });

  const handleEntryChange = (monthIdx: number, field: "s1" | "s2", value: string) => {
    setMonthEntries((prev) => ({
      ...prev,
      [monthIdx]: {
        ...(prev[monthIdx] || { s1: "", s2: "" }),
        [field]: value,
      },
    }));
  };

  const validationErrors = useMemo(() => {
    const errors: Record<number, boolean> = {};
    Object.entries(monthEntries).forEach(([monthStr, data]) => {
      const { s1, s2 } = data;
      const monthIdx = parseInt(monthStr, 10);
      if ((s1 && !s2) || (!s1 && s2)) {
        errors[monthIdx] = true;
      }
    });
    return errors;
  }, [monthEntries]);

  const hasErrors = Object.keys(validationErrors).length > 0;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (hasErrors) return;

    const validMonths: MonthEntry[] = [];
    Object.entries(monthEntries).forEach(([monthStr, data]) => {
      if (data.s1 && data.s2) {
        validMonths.push({
          month: parseInt(monthStr, 10) + 1, // API expects 1-12
          snapshot1_run_id: parseInt(data.s1, 10),
          snapshot2_run_id: parseInt(data.s2, 10),
        });
      }
    });

    if (validMonths.length === 0) {
      alert("Please select at least one month's snapshots.");
      return;
    }

    calcMutation.mutate({
      year,
      months: validMonths,
    });
  };

  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: 5 }, (_, i) => currentYear - 2 + i);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 overflow-y-auto py-10">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-3xl my-auto">
        <h2 className="text-xl font-bold text-white mb-4">Calculate Monthly Metrics - {year}</h2>
        
        <div className="mb-6">
          <label className="block text-gray-400 mb-2">Year</label>
          <select
            className="bg-gray-800 border border-gray-700 rounded p-2 text-white w-32"
            value={year}
            onChange={(e) => setYear(parseInt(e.target.value, 10))}
          >
            {years.map(y => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-2">
            {MONTHS.map((monthName, idx) => (
              <div key={idx} className="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <div className="flex flex-col md:flex-row gap-4 items-start md:items-center">
                  <div className="text-gray-300 font-medium w-32">
                    {monthName} {year}
                  </div>
                  
                  <div className="flex-1 flex gap-4 w-full">
                    <div className="flex-1">
                      <label className="block text-xs text-gray-500 mb-1">Snapshot 1 (Start)</label>
                      <select
                        className="w-full bg-gray-900 border border-gray-700 rounded p-2 text-white text-sm"
                        value={monthEntries[idx]?.s1 || ""}
                        onChange={(e) => handleEntryChange(idx, "s1", e.target.value)}
                        disabled={loadingRuns}
                      >
                        <option value="">Select Run...</option>
                        {scrapeRuns.map((run) => (
                          <option key={run.id} value={run.id}>
                            Run {run.id} ({format(new Date(run.started_at), 'MMM d, yy')}) - {run.status}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex-1">
                      <label className="block text-xs text-gray-500 mb-1">Snapshot 2 (End)</label>
                      <select
                        className="w-full bg-gray-900 border border-gray-700 rounded p-2 text-white text-sm"
                        value={monthEntries[idx]?.s2 || ""}
                        onChange={(e) => handleEntryChange(idx, "s2", e.target.value)}
                        disabled={loadingRuns}
                      >
                        <option value="">Select Run...</option>
                        {scrapeRuns.map((run) => (
                          <option key={run.id} value={run.id}>
                            Run {run.id} ({format(new Date(run.started_at), 'MMM d, yy')}) - {run.status}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                </div>
                {validationErrors[idx] && (
                  <p className="text-red-400 text-sm mt-2">
                    Both Run IDs must be entered, or both left empty.
                  </p>
                )}
              </div>
            ))}
          </div>

          <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-gray-800">
            <button
              type="button"
              className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 transition-colors disabled:opacity-50"
              disabled={calcMutation.isPending || hasErrors || loadingRuns}
            >
              {calcMutation.isPending ? "Calculating..." : "Calculate & Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
