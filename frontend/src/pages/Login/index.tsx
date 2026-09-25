import { useState, type FormEvent } from "react";
import { login, resetPassword, registerPoc, type User } from "../../api/auth";
import { LogIn, UserPlus, CheckCircle2, ArrowLeft } from "lucide-react";

interface LoginPageProps {
  onLoginSuccess: (user: User) => void;
}

type AuthView = "login" | "register" | "reset" | "register_success";

export default function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const [view, setView] = useState<AuthView>("login");
  
  // Login & Shared State
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  
  // Register State
  const [fullName, setFullName] = useState("");
  const [registerPassword, setRegisterPassword] = useState("");
  const [confirmRegisterPassword, setConfirmRegisterPassword] = useState("");
  
  // Reset Password State
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  
  // UI State
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleLoginSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;
    setLoading(true);
    setError(null);
    try {
      const res = await login(email, password);
      onLoginSuccess(res.user);
    } catch (err: any) {
      setError(err.message || "Invalid email or password. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!fullName.trim() || !email.trim() || !registerPassword) {
      setError("Please fill in all required fields.");
      return;
    }
    if (registerPassword.length < 6) {
      setError("Password must be at least 6 characters long.");
      return;
    }
    if (registerPassword !== confirmRegisterPassword) {
      setError("Passwords do not match. Please verify.");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await registerPoc({
        full_name: fullName.trim(),
        email: email.trim().toLowerCase(),
        password: registerPassword
      });
      setView("register_success");
    } catch (err: any) {
      setError(err.message || "Registration failed. Please check your details.");
    } finally {
      setLoading(false);
    }
  };

  const handleResetSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !newPassword) return;
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match. Please try again.");
      return;
    }
    if (newPassword.length < 6) {
      setError("Password must be at least 6 characters long.");
      return;
    }
    setLoading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      await resetPassword(email, newPassword);
      setSuccessMsg("Password reset successfully! Please sign in with your new password.");
      setView("login");
      setPassword(newPassword);
    } catch (err: any) {
      setError(err.message || "Failed to reset password. Please check your email.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center p-4 relative">
      {/* Background glow */}
      <div className="absolute inset-0 bg-gradient-to-tr from-purple-950/30 via-transparent to-pink-950/20 pointer-events-none" />

      <div className="relative w-full max-w-md bg-gray-900 border border-gray-800 rounded-2xl p-8 shadow-2xl backdrop-blur">
        {/* Brand header */}
        <div className="flex flex-col items-center text-center mb-6">
          <div className="w-16 h-16 rounded-2xl overflow-hidden p-0.5 shadow-lg shadow-purple-500/20 mb-4 flex items-center justify-center bg-gray-950 border border-gray-700">
            <img src="/wisdom_warriors_logo.jpg" alt="Wisdom Warriors" className="w-full h-full object-cover rounded-xl" />
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Wisdom Warriors</h1>
          <p className="text-gray-400 text-xs mt-1">
            {view === "login" && "Sign in to access analytics & micro units"}
            {view === "register" && "Register as a Micro Unit POC"}
            {view === "reset" && "Reset your account password"}
            {view === "register_success" && "Registration Request Received"}
          </p>
        </div>

        {/* View Switcher Tabs (Only when in login or register mode) */}
        {(view === "login" || view === "register") && (
          <div className="flex bg-gray-950 p-1 rounded-xl border border-gray-800 mb-6">
            <button
              type="button"
              onClick={() => {
                setView("login");
                setError(null);
                setSuccessMsg(null);
              }}
              className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all flex items-center justify-center gap-1.5 ${
                view === "login"
                  ? "bg-purple-800 text-white shadow-sm"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              <LogIn size={14} />
              Sign In
            </button>
            <button
              type="button"
              onClick={() => {
                setView("register");
                setError(null);
                setSuccessMsg(null);
              }}
              className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all flex items-center justify-center gap-1.5 ${
                view === "register"
                  ? "bg-purple-800 text-white shadow-sm"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              <UserPlus size={14} />
              Register as POC
            </button>
          </div>
        )}

        {successMsg && (
          <div className="p-3.5 bg-emerald-950/50 border border-emerald-800/80 text-emerald-300 text-sm rounded-xl mb-6 flex items-start gap-2">
            <span className="text-emerald-400 font-bold">✓</span>
            <span>{successMsg}</span>
          </div>
        )}

        {error && (
          <div className="p-3.5 bg-red-950/50 border border-red-800/80 text-red-300 text-sm rounded-xl mb-6 flex items-start gap-2">
            <span className="text-red-400 font-bold">⚠️</span>
            <span className="text-xs leading-relaxed">{error}</span>
          </div>
        )}

        {/* 1. LOGIN VIEW */}
        {view === "login" && (
          <form onSubmit={handleLoginSubmit} className="space-y-4">
            <div>
              <label className="block text-gray-300 text-xs font-semibold uppercase tracking-wider mb-1.5">
                Email Address
              </label>
              <input
                type="email"
                placeholder="example@gmail.com"
                className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-2.5 text-white placeholder-gray-600 text-sm focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-all"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoFocus
                required
              />
            </div>

            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label className="block text-gray-300 text-xs font-semibold uppercase tracking-wider">
                  Password
                </label>
                <button
                  type="button"
                  onClick={() => {
                    setView("reset");
                    setError(null);
                    setSuccessMsg(null);
                  }}
                  className="text-xs text-purple-400 hover:text-purple-300 transition-colors"
                >
                  Forgot password?
                </button>
              </div>
              <input
                type="password"
                placeholder="••••••••"
                className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-2.5 text-white placeholder-gray-600 text-sm focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-all"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 py-3 px-4 bg-gradient-to-r from-purple-700 to-indigo-600 hover:from-purple-600 hover:to-indigo-500 text-white font-medium rounded-xl shadow-lg shadow-purple-900/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Signing in...</span>
                </>
              ) : (
                <span>Sign In</span>
              )}
            </button>
          </form>
        )}

        {/* 2. REGISTER AS POC VIEW */}
        {view === "register" && (
          <form onSubmit={handleRegisterSubmit} className="space-y-3.5">
            <div>
              <label className="block text-gray-300 text-xs font-semibold uppercase tracking-wider mb-1.5">
                Full Name
              </label>
              <input
                type="text"
                placeholder="e.g. Dhiren Patel"
                className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-2 text-white placeholder-gray-600 text-sm focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-all"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                autoFocus
                required
              />
            </div>

            <div>
              <label className="block text-gray-300 text-xs font-semibold uppercase tracking-wider mb-1.5">
                Email Address
              </label>
              <input
                type="email"
                placeholder="example@gmail.com"
                className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-2 text-white placeholder-gray-600 text-sm focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-all"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="block text-gray-300 text-xs font-semibold uppercase tracking-wider mb-1.5">
                Password
              </label>
              <input
                type="password"
                placeholder="Minimum 6 characters"
                className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-2 text-white placeholder-gray-600 text-sm focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-all"
                value={registerPassword}
                onChange={(e) => setRegisterPassword(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="block text-gray-300 text-xs font-semibold uppercase tracking-wider mb-1.5">
                Confirm Password
              </label>
              <input
                type="password"
                placeholder="Re-enter password"
                className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-2 text-white placeholder-gray-600 text-sm focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-all"
                value={confirmRegisterPassword}
                onChange={(e) => setConfirmRegisterPassword(e.target.value)}
                required
              />
            </div>

            <p className="text-[11px] text-gray-400 leading-relaxed bg-purple-950/30 border border-purple-850/50 p-2.5 rounded-lg">
              ℹ️ After registration, an admin notification will be sent for review. Your POC account will be activated upon Admin approval.
            </p>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 py-3 px-4 bg-gradient-to-r from-purple-700 to-indigo-600 hover:from-purple-600 hover:to-indigo-500 text-white font-medium rounded-xl shadow-lg shadow-purple-900/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Submitting Request...</span>
                </>
              ) : (
                <span>Register Request for Approval</span>
              )}
            </button>
          </form>
        )}

        {/* 3. REGISTER SUCCESS VIEW */}
        {view === "register_success" && (
          <div className="text-center py-4 space-y-4">
            <div className="w-14 h-14 rounded-2xl bg-emerald-950/80 border border-emerald-700/60 text-emerald-400 flex items-center justify-center mx-auto shadow-lg shadow-emerald-950/50">
              <CheckCircle2 size={32} />
            </div>

            <div className="space-y-1.5">
              <h3 className="text-lg font-bold text-white">Registration Request Sent!</h3>
              <p className="text-xs text-gray-300 leading-relaxed max-w-sm mx-auto">
                Thank you, <span className="text-white font-semibold">{fullName}</span>! Your POC registration request has been submitted to the Admin for approval.
              </p>
            </div>

            <div className="p-3.5 bg-gray-950 border border-gray-800 rounded-xl text-left text-xs text-gray-400 space-y-1">
              <div className="flex justify-between text-gray-300">
                <span>Account Email:</span>
                <span className="font-semibold text-white">{email}</span>
              </div>
              <div className="flex justify-between text-gray-300">
                <span>Status:</span>
                <span className="text-amber-400 font-semibold">Pending Admin Approval</span>
              </div>
            </div>

            <button
              type="button"
              onClick={() => {
                setView("login");
                setError(null);
                setSuccessMsg(null);
              }}
              className="w-full py-2.5 px-4 bg-gray-800 hover:bg-gray-700 text-white font-medium rounded-xl text-xs transition-colors flex items-center justify-center gap-2"
            >
              <ArrowLeft size={14} />
              Return to Sign In
            </button>
          </div>
        )}

        {/* 4. RESET PASSWORD VIEW */}
        {view === "reset" && (
          <form onSubmit={handleResetSubmit} className="space-y-4">
            <div>
              <label className="block text-gray-300 text-xs font-semibold uppercase tracking-wider mb-1.5">
                Account Email
              </label>
              <input
                type="email"
                placeholder="example@gmail.com"
                className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-2.5 text-white placeholder-gray-600 text-sm focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-all"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoFocus
                required
              />
            </div>

            <div>
              <label className="block text-gray-300 text-xs font-semibold uppercase tracking-wider mb-1.5">
                New Password
              </label>
              <input
                type="password"
                placeholder="Minimum 6 characters"
                className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-2.5 text-white placeholder-gray-600 text-sm focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-all"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="block text-gray-300 text-xs font-semibold uppercase tracking-wider mb-1.5">
                Confirm New Password
              </label>
              <input
                type="password"
                placeholder="Re-enter new password"
                className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-2.5 text-white placeholder-gray-600 text-sm focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-all"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 py-3 px-4 bg-gradient-to-r from-purple-700 to-indigo-600 hover:from-purple-600 hover:to-indigo-500 text-white font-medium rounded-xl shadow-lg shadow-purple-900/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Updating password...</span>
                </>
              ) : (
                <span>Reset Password</span>
              )}
            </button>

            <div className="text-center pt-2">
              <button
                type="button"
                onClick={() => {
                  setView("login");
                  setError(null);
                }}
                className="text-xs text-gray-400 hover:text-white transition-colors"
              >
                ← Back to Sign In
              </button>
            </div>
          </form>
        )}

        <div className="mt-6 pt-6 border-t border-gray-800 text-center text-xs text-gray-500">
          Wisdom Warriors Analytics Portal
        </div>
      </div>
    </div>
  );
}
