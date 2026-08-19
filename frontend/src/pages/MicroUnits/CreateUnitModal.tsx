import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createMicroUnit } from "../../api/microUnits";

interface CreateUnitModalProps {
  onClose: () => void;
}

export default function CreateUnitModal({ onClose }: CreateUnitModalProps) {
  const [unitNumber, setUnitNumber] = useState("");
  const [name, setName] = useState("");
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: (body: { unit_number: number; name: string }) => createMicroUnit(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["microUnits"] });
      onClose();
    },
    onError: (err: any) => {
      alert(`Error creating unit: ${err.message}`);
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!unitNumber || !name) return;
    createMutation.mutate({
      unit_number: parseInt(unitNumber, 10),
      name,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md">
        <h2 className="text-xl font-bold text-white mb-4">Create Micro Unit</h2>
        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label className="block text-gray-400 mb-2">Unit Number</label>
            <input
              type="number"
              className="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white"
              value={unitNumber}
              onChange={(e) => setUnitNumber(e.target.value)}
              required
            />
          </div>
          <div className="mb-6">
            <label className="block text-gray-400 mb-2">Unit Name</label>
            <input
              type="text"
              className="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
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
              disabled={createMutation.isPending}
            >
              {createMutation.isPending ? "Creating..." : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
