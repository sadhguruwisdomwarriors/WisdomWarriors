import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { updateMicroUnit, type MicroUnit } from "../../api/microUnits";
import { getUsers } from "../../api/auth";

interface AssignPocModalProps {
  onClose: () => void;
  microUnits: MicroUnit[];
  defaultUnitId?: number;
}

export default function AssignPocModal({ onClose, microUnits, defaultUnitId }: AssignPocModalProps) {
  const [selectedUnitId, setSelectedUnitId] = useState<string>(defaultUnitId?.toString() || "");
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const queryClient = useQueryClient();

  const { data: users = [], isLoading: loadingUsers } = useQuery({
    queryKey: ["users"],
    queryFn: getUsers,
  });

  const assignMutation = useMutation({
    mutationFn: ({ unitId, poc_user_id }: { unitId: number; poc_user_id: number }) =>
      updateMicroUnit(unitId, { poc_user_id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["microUnits"] });
      onClose();
    },
    onError: (err: any) => {
      alert(`Error assigning POC: ${err.message}`);
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!selectedUnitId || !selectedUserId) return;
    assignMutation.mutate({
      unitId: parseInt(selectedUnitId, 10),
      poc_user_id: parseInt(selectedUserId, 10),
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md">
        <h2 className="text-xl font-bold text-white mb-4">Assign POC</h2>
        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label className="block text-gray-400 mb-2">Micro Unit</label>
            <select
              className="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white"
              value={selectedUnitId}
              onChange={(e) => setSelectedUnitId(e.target.value)}
              required
            >
              <option value="" disabled>Select Micro Unit...</option>
              {microUnits.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.name} (Unit {unit.unit_number})
                </option>
              ))}
            </select>
          </div>
          <div className="mb-6">
            <label className="block text-gray-400 mb-2">POC User</label>
            <select
              className="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white"
              value={selectedUserId}
              onChange={(e) => setSelectedUserId(e.target.value)}
              required
              disabled={loadingUsers}
            >
              <option value="" disabled>Select POC...</option>
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.full_name} ({user.email})
                </option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-3">
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
              disabled={assignMutation.isPending || !selectedUnitId || !selectedUserId}
            >
              {assignMutation.isPending ? "Assigning..." : "Assign"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
