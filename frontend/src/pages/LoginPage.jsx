import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "../hooks/useAuth"

const LoginPage = () => {
  const { login } = useAuth()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  const handleSubmit = async (event) => {
    event.preventDefault()
    try {
      await login(email, password)
      navigate("/dashboard")
    } catch (err) {
      setError("Login failed. Check credentials.")
    }
  }

  return (
    <div className="mx-auto max-w-md py-16 px-6">
      <div className="rounded-3xl bg-panel p-10 shadow-2xl">
        <h1 className="text-3xl font-semibold">Sign in</h1>
        <p className="mt-3 text-slate-400">Access your intelligent CI/CD dashboard.</p>
        <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
          <label className="block">
            <span className="text-slate-300">Email</span>
            <input value={email} onChange={(e) => setEmail(e.target.value)} className="mt-2 w-full rounded-2xl border border-slate-700 bg-slate-900 px-4 py-3 text-white" />
          </label>
          <label className="block">
            <span className="text-slate-300">Password</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-2 w-full rounded-2xl border border-slate-700 bg-slate-900 px-4 py-3 text-white" />
          </label>
          {error && <p className="text-sm text-rose-400">{error}</p>}
          <button type="submit" className="w-full rounded-full bg-accent px-6 py-3 font-medium text-white">Login</button>
        </form>
      </div>
    </div>
  )
}

export default LoginPage
