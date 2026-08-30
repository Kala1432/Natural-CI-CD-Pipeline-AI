import { createContext, useCallback, useContext, useEffect, useState } from "react"
import api, { setAuthToken } from "../api"

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  // On mount, restore session from cookie
  useEffect(() => {
    api.get("/auth/me")
      .then((res) => setUser(res.data.user))
      .catch(() => {
        setUser(null)
      })
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email, password) => {
    const res = await api.post("/auth/login", { email, password })
    setUser(res.data.user)
    return res.data.user
  }, [])

  const register = useCallback(async (email, password, name) => {
    const res = await api.post("/auth/register", { email, password, name })
    if (res.data.user) {
      setUser(res.data.user)
    }
    return res.data
  }, [])

  const verifyEmail = useCallback(async (email, otp) => {
    const res = await api.post("/auth/verify-email", { email, otp })
    setUser(res.data.user)
    return res.data.user
  }, [])

  const googleSignIn = useCallback(async (idToken) => {
    const res = await api.post("/auth/google", { id_token: idToken })
    setUser(res.data.user)
    return res.data.user
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout")
    } catch (e) {
      console.error(e)
    }
    setUser(null)
  }, [])

  const refreshUser = useCallback(async () => {
    const res = await api.get("/auth/me")
    setUser(res.data.user)
    return res.data.user
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, register, verifyEmail, googleSignIn, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider")
  return ctx
}
