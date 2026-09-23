import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Check, Trash2, UserCheck, Clock, Building } from "lucide-react";
import { getPendingRegistrations, approveUser, rejectUser, type User } from "../../api/auth";
import type { MicroUnit } from "../../api/microUnits";

interface PendingApprovalsModalProps {
  onClose: () => void;
  microUnits: MicroUnit[];
}

export default function PendingApprovalsModal({ onClose, microUnits }: PendingApprovalsModalProps) {
  const queryClient = useQueryClient();
  const [selectedUnits, setSelectedUnits] = useState<Record<number, number>>({});
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const { data: pendingUsers = [], isLoading, error } = useQuery({
    queryKey: ["pendingRegistrations"],
    queryFn: getPendingRegistrations,
  });

  const approveMutation = useMutation({
    mutationFn: ({ userId, microUnitId }: { userId: number; microUnitId?: number }) =>
      approveUser(userId, microUnitId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["pendingRegistrations"] });
      queryClient.invalidateQueries({ queryKey: ["users"] });
      queryClient.invalidateQueries({ queryKey: ["microUnits"] });
      setActionSuccess(data.message);
      setTimeout(() => setActionSuccess(null), 4000);
    },
    onError: (err: any) => {
      alert(`Error approving user: ${err.message}`);
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (userId: number) => rejectUser(userId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["pendingRegistrations"] });
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setActionSuccess(data.message);
      setTimeout(() => setActionSuccess(null), 4000);
    },
    onError: (err: any) => {
      alert(`Error rejecting user: ${err.message}`);
    },
  });

  const handleUnitChange = (userId: number, unitIdStr: string) => {
    const unitId = parseInt(unitIdStr, 10);
    setSelectedUnits(prev => ({
      ...prev,
      [userId]: isNaN(unitId) ? 0 : unitId
    }));
  };

  const handleApprove = (user: User) => {
    const chosenUnitId = selectedUnits[user.id] || undefined;
    approveMutation.mutate({ userId: user.id, microUnitId: chosenUnitId });
  };

  const handleReject = (user: User) => {
    if (confirm(`Are you sure you want to decline registration for ${user.full_name} (${user.email})?`)) {
      rejectMutation.mutate(user.id);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-5 border-b border-gray-800 flex items-center justify-between bg-gray-950/80">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-950/60 border border-amber-700/50 flex items-center justify-center text-amber-400">
              <UserCheck size={20} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <span>Pending POC Registrations</span>
                {pendingUsers.length > 0 && (
                  <span className="px-2 py-0.5 rounded-full text-xs font-extrabold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                    {pendingUsers.length} Pending
                  </span>
                )}
              </h2>
              <p className="text-xs text-gray-400 mt-0.5">
                Review and approve POC sign-up requests to grant them login access and assign them to Micro Units
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 overflow-y-auto flex-1 space-y-4">
          {actionSuccess && (
            <div className="p-3 bg-emerald-950/60 border border-emerald-800/80 text-emerald-300 text-xs rounded-xl flex items-center gap-2">
              <span className="font-bold">✓</span>
              <span>{actionSuccess}</span>
            </div>
          )}

          {isLoading ? (
            <div className="py-12 text-center text-gray-400 text-sm">
              Loading pending requests...
            </div>
          ) : error ? (
            <div className="py-12 text-center text-red-400 text-sm">
              Failed to load pending registrations.
            </div>
          ) : pendingUsers.length === 0 ? (
            <div className="py-12 text-center space-y-2">
              <div className="w-12 h-12 rounded-full bg-gray-800 flex items-center justify-center mx-auto text-gray-500">
                <Check size={22} className="text-emerald-400" />
              </div>
              <h3 className="text-sm font-semibold text-white">No Pending Registrations</h3>
              <p className="text-xs text-gray-500 max-w-sm mx-auto">
                All prospective POC sign-up requests have been reviewed. New registration requests will appear here.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {pendingUsers.map((user) => {
                const isApproving = approveMutation.isPending && approveMutation.variables?.userId === user.id;
                const isRejecting = rejectMutation.isPending && rejectMutation.variables === user.id;

                return (
                  <div
                    key={user.id}
                    className="bg-gray-950 border border-gray-800 hover:border-gray-700/80 rounded-xl p-4 transition-colors space-y-3"
                  >
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl bg-purple-950/60 border border-purple-700/50 text-purple-200 flex items-center justify-center font-bold text-sm">
                          {user.full_name.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <div className="text-white font-bold text-sm flex items-center gap-2">
                            <span>{user.full_name}</span>
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-purple-900/40 text-purple-300 border border-purple-800/40 uppercase">
                              POC Request
                            </span>
                          </div>
                          <div className="text-xs text-gray-400">{user.email}</div>
                        </div>
                      </div>

                      {user.created_at && (
                        <div className="text-[11px] text-gray-500 flex items-center gap-1">
                          <Clock size={12} />
                          <span>{new Date(user.created_at).toLocaleDateString()}</span>
                        </div>
                      )}
                    </div>

                    <div className="pt-2 border-t border-gray-850 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
                      {/* Optional Unit Selection */}
                      <div className="flex-1 flex items-center gap-2">
                        <Building size={14} className="text-gray-500 flex-shrink-0" />
                        <select
                          className="bg-gray-900 border border-gray-700 rounded-lg px-2.5 py-1.5 text-xs text-white flex-1 focus:outline-none focus:border-purple-500"
                          value={selectedUnits[user.id] || ""}
                          onChange={(e) => handleUnitChange(user.id, e.target.value)}
                        >
                          <option value="">Assign to Micro Unit (Optional)...</option>
                          {microUnits.map(unit => (
                            <option key={unit.id} value={unit.id}>
                              {unit.name} (Unit {unit.unit_number}){unit.poc_name ? ` - Current POC: ${unit.poc_name}` : ""}
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Action buttons */}
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <button
                          type="button"
                          disabled={isRejecting || isApproving}
                          onClick={() => handleReject(user)}
                          className="px-3 py-1.5 bg-red-950/50 hover:bg-red-900/60 text-red-300 border border-red-800/50 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-50"
                        >
                          <Trash2 size={13} />
                          {isRejecting ? "Declining..." : "Decline"}
                        </button>
                        <button
                          type="button"
                          disabled={isApproving || isRejecting}
                          onClick={() => handleApprove(user)}
                          className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg shadow-sm shadow-emerald-950 transition-colors flex items-center gap-1.5 disabled:opacity-50"
                        >
                          <Check size={14} />
                          {isApproving ? "Approving..." : "Approve & Activate"}
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-800 bg-gray-950/90 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-medium rounded-xl transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
