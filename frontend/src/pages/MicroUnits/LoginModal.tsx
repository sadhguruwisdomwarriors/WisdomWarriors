import { useState, type FormEvent } from "react";
import { login, type User } from "../../api/auth";

interface LoginModalProps {
  onClose: () => void;
  onSuccess: (user: User) => void;
}

export default function LoginModal({ onClose, onSuccess }: LoginModalProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;
    setLoading(true);
    setError(null);
    try {
      const res = await login(email, password);
      onSuccess(res.user);
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to log in");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md">
        <div className="flex items-center gap-2 mb-4">
          <img src="/wisdom_warriors_logo.jpg" alt="Wisdom Warriors" className="w-6 h-6 rounded-full object-cover border border-gray-700" />
          <h2 className="text-xl font-bold text-white">Log In to Wisdom Warriors</h2>
        </div>
        <p className="text-gray-400 text-xs mb-4">Log in as Admin to manage units, or as POC to view your unit dashboard.</p>

        {error && (
          <div className="p-3 bg-red-900/40 border border-red-800 text-red-300 rounded text-sm mb-4">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-gray-400 text-sm mb-1">Email Address</label>
            <input
              type="email"
              placeholder="example@gmail.com"
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
              placeholder="Enter password"
              className="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white text-sm"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
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
              disabled={loading}
            >
              {loading ? "Logging in..." : "Log In"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
