import axios from "axios"

// In dev (npm run dev), Vite proxies /api → localhost:5000, so relative path works.
// In production (Flask serves the built frontend), relative path also works.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
  headers: { "Content-Type": "application/json" },
  withCredentials: true,
})

export const setAuthToken = (token) => {
  if (token) {
    api.defaults.headers.common["Authorization"] = `Bearer ${token}`
  } else {
    delete api.defaults.headers.common["Authorization"]
  }
}

// Request interceptor: attach CSRF token for state-changing requests
api.interceptors.request.use((config) => {
  if (config.method && ["post", "put", "patch", "delete"].includes(config.method.toLowerCase())) {
    if (typeof document !== "undefined") {
      const match = document.cookie.match(/(?:^|;\s*)(?:csrf_access_token|csrf_token)=([^;]*)/);
      if (match) {
        config.headers["X-CSRF-TOKEN"] = decodeURIComponent(match[1]);
      }
    }
  }
  return config;
});

// Response interceptor: surface error messages cleanly
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const message =
      err.response?.data?.error ||
      err.response?.data?.message ||
      err.message ||
      "An unexpected error occurred"
    return Promise.reject(new Error(message))
  }
)

export default api
