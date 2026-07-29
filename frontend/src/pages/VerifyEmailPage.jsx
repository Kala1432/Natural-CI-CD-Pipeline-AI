import { useState } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"
import api from "../api"
import { useAuth } from "../hooks/AuthContext"

const VerifyEmailPage = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const { verifyEmail } = useAuth()
  const [email, setEmail] = useState(location.state?.email || "")
  const [otp, setOtp] = useState("")
  const [message, setMessage] = useState("We sent a six-digit code to your email.")
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleVerify = async (e) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await verifyEmail(email, otp)
      navigate("/dashboard")
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const resend = async () => {
    setError(null)
    setMessage(null)
    try {
      const res = await api.post("/auth/resend-verification", { email })
      setMessage(res.data.message)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm rounded-2xl border border-subtle bg-[#111827] p-8 shadow-2xl">
        <h1 className="text-2xl font-semibold text-white">Verify your email</h1>
        <p className="mt-2 text-sm text-slate-400">{message}</p>
        <form onSubmit={handleVerify} className="mt-6 space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-300">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-300">Verification code</label>
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              maxLength={6}
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="123456"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3.5 py-2.5 text-center font-mono text-xl tracking-[0.4em] text-white outline-none focus:border-indigo-500"
            />
          </div>
          {error && <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3.5 py-2.5 text-sm text-rose-400">{error}</div>}
          <button
            type="submit"
            disabled={loading || otp.length !== 6}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-60"
          >
            {loading ? "Verifying…" : "Verify email"}
          </button>
        </form>
        <div className="mt-5 flex justify-between text-sm">
          <button onClick={resend} className="text-indigo-400 hover:text-indigo-300">Resend code</button>
          <Link to="/login" className="text-slate-400 hover:text-white">Back to sign in</Link>
        </div>
      </div>
    </div>
  )
}

export default VerifyEmailPage
