import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createUser, type CreateUserBody } from "../../api/auth";

interface CreateUserModalProps {
  onClose: () => void;
}

export default function CreateUserModal({ onClose }: CreateUserModalProps) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("POC");
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: (body: CreateUserBody) => createUser(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      alert(`User ${fullName} created successfully! You can now assign them as POC.`);
      onClose();
    },
    onError: (err: any) => {
      alert(`Error creating user: ${err.message}`);
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!fullName || !email || !password) return;
    createMutation.mutate({
      full_name: fullName,
      email,
      password,
      role,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md">
        <h2 className="text-xl font-bold text-white mb-4">Create New User (POC / Admin)</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-gray-400 text-sm mb-1">Full Name</label>
            <input
              type="text"
              placeholder="e.g. Arun Kumar"
              className="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white text-sm"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block text-gray-400 text-sm mb-1">Email Address</label>
            <input
              type="email"
              placeholder="e.g. arun@wisdomwarriors.com"
              className="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white text-sm"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block text-gray-400 text-sm mb-1">Password</label>
            <input
              type="password"
              placeholder="Minimum 6 characters"
              className="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white text-sm"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block text-gray-400 text-sm mb-1">Role</label>
            <select
              className="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white text-sm"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              <option value="POC">Point of Coordinator (POC)</option>
              <option value="ADMIN">Admin</option>
            </select>
          </div>
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-800">
            <button
              type="button"
              className="px-4 py-2 bg-gray-700 text-white text-sm rounded hover:bg-gray-600 transition-colors"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-purple-600 text-white text-sm rounded hover:bg-purple-700 transition-colors disabled:opacity-50"
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
