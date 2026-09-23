import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X, UserPlus, Mail, UserCheck } from "lucide-react";
import { createUser, type CreateUserBody } from "../../api/auth";

interface CreateUserModalProps {
  onClose: () => void;
}

export default function CreateUserModal({ onClose }: CreateUserModalProps) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("POC");
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: (body: CreateUserBody) => createUser(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      queryClient.invalidateQueries({ queryKey: ["microUnits"] });
      alert(`User "${fullName}" created successfully! You can now assign them as POC to a Micro Unit.`);
      onClose();
    },
    onError: (err: any) => {
      alert(`Error creating user: ${err.message}`);
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!fullName.trim() || !email.trim()) return;
    createMutation.mutate({
      full_name: fullName.trim(),
      email: email.trim().toLowerCase(),
      role,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 w-full max-w-md shadow-2xl overflow-hidden space-y-5">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-gray-800 pb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-purple-950/60 border border-purple-700/50 flex items-center justify-center text-purple-400">
              <UserPlus size={20} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">Create New User / POC</h2>
              <p className="text-xs text-gray-400 mt-0.5">
                Add an admin or POC user directly to the database
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

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-gray-300 text-xs font-semibold uppercase tracking-wider mb-1.5">
              Full Name
            </label>
            <div className="relative flex items-center">
              <UserCheck size={14} className="absolute left-3 text-gray-500 pointer-events-none" />
              <input
                type="text"
                placeholder="e.g. Arun Kumar"
                className="w-full bg-gray-950 border border-gray-800 rounded-xl pl-9 pr-3.5 py-2.5 text-white placeholder-gray-600 text-sm focus:outline-none focus:border-purple-500 transition-all"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                autoFocus
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-gray-300 text-xs font-semibold uppercase tracking-wider mb-1.5">
              Email Address
            </label>
            <div className="relative flex items-center">
              <Mail size={14} className="absolute left-3 text-gray-500 pointer-events-none" />
              <input
                type="email"
                placeholder="example@gmail.com"
                className="w-full bg-gray-950 border border-gray-800 rounded-xl pl-9 pr-3.5 py-2.5 text-white placeholder-gray-600 text-sm focus:outline-none focus:border-purple-500 transition-all"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-gray-300 text-xs font-semibold uppercase tracking-wider mb-1.5">
              Role
            </label>
            <select
              className="w-full bg-gray-950 border border-gray-800 rounded-xl px-3.5 py-2.5 text-white text-sm focus:outline-none focus:border-purple-500 transition-all"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              <option value="POC">Point of Contact (POC)</option>
              <option value="ADMIN">Administrator (Full Access)</option>
            </select>
          </div>

          <div className="p-3 bg-purple-950/30 border border-purple-850/50 rounded-xl text-xs text-gray-400 leading-relaxed">
            💡 <span className="text-purple-300 font-semibold">Note:</span> Prospective POCs can also directly self-register on the portal login page with their own chosen password.
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t border-gray-800">
            <button
              type="button"
              className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-medium rounded-xl transition-colors"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-5 py-2 bg-gradient-to-r from-purple-700 to-indigo-600 hover:from-purple-600 hover:to-indigo-500 text-white text-xs font-semibold rounded-xl shadow-md shadow-purple-950 transition-all disabled:opacity-50"
              disabled={createMutation.isPending}
            >
              {createMutation.isPending ? "Creating..." : "Create User"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
