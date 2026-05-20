import { useState } from "react"
import { useNavigate } from "react-router-dom"
import api from "../api"

const RegisterPage = () => {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [name, setName] = useState("")
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  const handleRegister = async (event) => {
    event.preventDefault()
    try {
      await api.post("/auth/register", { email, password, name })
      setSuccess(true)
      setTimeout(() => navigate("/login"), 1000)
    } catch (err) {
      setError("Registration failed.")
    }
  }

  return (
    <div className="mx-auto max-w-md py-16 px-6">
      <div className="rounded-3xl bg-panel p-10 shadow-2xl">
        <h1 className="text-3xl font-semibold">Create an account</h1>
        <form className="mt-8 space-y-5" onSubmit={handleRegister}>
          <label className="block">
            <span className="text-slate-300">Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} className="mt-2 w-full rounded-2xl border border-slate-700 bg-slate-900 px-4 py-3 text-white" />
          </label>
          <label className="block">
            <span className="text-slate-300">Email</span>
            <input value={email} onChange={(e) => setEmail(e.target.value)} className="mt-2 w-full rounded-2xl border border-slate-700 bg-slate-900 px-4 py-3 text-white" />
          </label>
          <label className="block">
            <span className="text-slate-300">Password</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-2 w-full rounded-2xl border border-slate-700 bg-slate-900 px-4 py-3 text-white" />
          </label>
          {error && <p className="text-sm text-rose-400">{error}</p>}
          {success && <p className="text-sm text-emerald-400">Registration successful! Redirecting...</p>}
          <button type="submit" className="w-full rounded-full bg-accent px-6 py-3 font-medium text-white">Register</button>
        </form>
      </div>
    </div>
  )
}

export default RegisterPage
