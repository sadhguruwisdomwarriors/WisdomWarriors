import { useState, useEffect, useMemo, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchScrapeRuns, calculateMonthlyMetrics, fetchConfiguredRuns, type MonthEntry } from "../../api/microUnits";
import { format } from "date-fns";

interface CalculateMetricsModalProps {
  onClose: () => void;
}

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

export default function CalculateMetricsModal({ onClose }: CalculateMetricsModalProps) {
  const loadLocalRuns = (targetYear: number): Record<number, { s1: string; s2: string }> => {
    try {
      const saved = localStorage.getItem(`wisdom_warriors_metrics_runs_${targetYear}`);
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  };

  const [year, setYear] = useState<number>(new Date().getFullYear());
  const [monthEntries, setMonthEntries] = useState<Record<number, { s1: string; s2: string }>>(() =>
    loadLocalRuns(new Date().getFullYear())
  );
  const queryClient = useQueryClient();

  const { data: scrapeRuns = [], isLoading: loadingRuns } = useQuery({
    queryKey: ["scrapeRuns"],
    queryFn: fetchScrapeRuns,
  });

  const { data: configuredRuns } = useQuery({
    queryKey: ["configuredRuns", year],
    queryFn: () => fetchConfiguredRuns(year),
  });

  // When year changes, load local runs for that year
  useEffect(() => {
    const local = loadLocalRuns(year);
    setMonthEntries(local);
  }, [year]);

  // When API configuredRuns arrives, merge and save
  useEffect(() => {
    if (configuredRuns && Object.keys(configuredRuns).length > 0) {
      const apiEntries: Record<number, { s1: string; s2: string }> = {};
      Object.entries(configuredRuns).forEach(([monthStr, data]) => {
        const m = parseInt(monthStr, 10);
        if (data.snapshot1_run_id && data.snapshot2_run_id) {
          apiEntries[m - 1] = {
            s1: String(data.snapshot1_run_id),
            s2: String(data.snapshot2_run_id),
          };
        }
      });
      setMonthEntries((prev) => {
        const merged = { ...apiEntries, ...prev };
        try {
          localStorage.setItem(`wisdom_warriors_metrics_runs_${year}`, JSON.stringify(merged));
        } catch {}
        return merged;
      });
    }
  }, [configuredRuns, year]);

  const calcMutation = useMutation({
    mutationFn: calculateMonthlyMetrics,
    onSuccess: () => {
      try {
        localStorage.setItem(`wisdom_warriors_metrics_runs_${year}`, JSON.stringify(monthEntries));
      } catch {}
      queryClient.invalidateQueries({ queryKey: ["microUnits"] });
      queryClient.invalidateQueries({ queryKey: ["configuredRuns"] });
      alert("Metrics calculated successfully!");
      onClose();
    },
    onError: (err: any) => {
      alert(`Error calculating metrics: ${err.message}`);
    },
  });

  const handleEntryChange = (monthIdx: number, field: "s1" | "s2", value: string) => {
    setMonthEntries((prev) => {
      const updated = {
        ...prev,
        [monthIdx]: {
          ...(prev[monthIdx] || { s1: "", s2: "" }),
          [field]: value,
        },
      };
      try {
        localStorage.setItem(`wisdom_warriors_metrics_runs_${year}`, JSON.stringify(updated));
      } catch {}
      return updated;
    });
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

  const handleClearAll = () => {
    if (confirm(`Are you sure you want to clear all Run IDs and reset all metrics for ${year}?`)) {
      setMonthEntries({});
      try {
        localStorage.removeItem(`wisdom_warriors_metrics_runs_${year}`);
      } catch {}
      calcMutation.mutate({
        year,
        months: [],
      });
    }
  };

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
      if (confirm(`No Run IDs are selected. Do you want to clear/reset all monthly metrics for ${year}?`)) {
        calcMutation.mutate({
          year,
          months: [],
        });
      }
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
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-xl font-bold text-white">Calculate Monthly Metrics - {year}</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Select Snapshot 1 and Snapshot 2 for active months. Empty months will be cleared.
            </p>
          </div>
          <button
            type="button"
            onClick={handleClearAll}
            className="text-xs text-red-400 hover:text-red-300 hover:bg-red-950/40 px-2.5 py-1.5 rounded-lg border border-red-800/40 transition-colors"
          >
            Clear All Months
          </button>
        </div>
        
        <div className="mb-6">
          <label className="block text-gray-400 mb-2 text-sm font-medium">Year</label>
          <select
            className="bg-gray-800 border border-gray-700 rounded p-2 text-white w-32 text-sm"
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
