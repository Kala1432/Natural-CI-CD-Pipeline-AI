import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import api from "../api"

const ForgotPasswordPage = () => {
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [otp, setOtp] = useState("")
  const [password, setPassword] = useState("")
  const [requested, setRequested] = useState(false)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const requestCode = async (e) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await api.post("/auth/forgot-password", { email })
      setMessage(res.data.message)
      setRequested(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const resetPassword = async (e) => {
    e.preventDefault()
    if (password.length < 6) {
      setError("Password must be at least 6 characters")
      return
    }
    setError(null)
    setLoading(true)
    try {
      await api.post("/auth/reset-password", {
        email,
        otp,
        new_password: password,
      })
      navigate("/login", { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm rounded-2xl border border-subtle bg-[#111827] p-8 shadow-2xl">
        <h1 className="text-2xl font-semibold text-white">Reset your password</h1>
        <p className="mt-2 text-sm text-slate-400">
          {requested ? "Enter the code from your email and choose a new password." : "We’ll email you a one-time reset code."}
        </p>
        <form onSubmit={requested ? resetPassword : requestCode} className="mt-6 space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-300">Email</label>
            <input
              type="email"
              required
              disabled={requested}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-white outline-none focus:border-indigo-500 disabled:opacity-60"
            />
          </div>
          {requested && (
            <>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">Reset code</label>
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  required
                  maxLength={6}
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-3.5 py-2.5 text-center font-mono text-xl tracking-[0.4em] text-white outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">New password</label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Min. 6 characters"
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                />
              </div>
            </>
          )}
          {message && <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3.5 py-2.5 text-sm text-emerald-400">{message}</div>}
          {error && <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3.5 py-2.5 text-sm text-rose-400">{error}</div>}
          <button
            type="submit"
            disabled={loading || (requested && otp.length !== 6)}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-60"
          >
            {loading ? "Please wait…" : requested ? "Reset password" : "Send reset code"}
          </button>
        </form>
        <p className="mt-5 text-center text-sm">
          <Link to="/login" className="text-indigo-400 hover:text-indigo-300">Back to sign in</Link>
        </p>
      </div>
    </div>
  )
}

export default ForgotPasswordPage
