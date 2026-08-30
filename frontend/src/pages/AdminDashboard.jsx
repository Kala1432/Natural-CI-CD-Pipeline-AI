import { useEffect, useState } from "react"
import api from "../api"

const ShieldCheckIcon = (props) => (
  <svg {...props} fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 01-1.043 3.296 3.745 3.745 0 01-3.296 1.043A3.745 3.745 0 0112 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 01-3.296-1.043 3.745 3.745 0 01-1.043-3.296A3.745 3.745 0 013 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 011.043-3.296 3.746 3.746 0 013.296-1.043A3.746 3.746 0 0112 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 013.296 1.043 3.746 3.746 0 011.043 3.296A3.745 3.745 0 0121 12z" />
  </svg>
)

const UsersIcon = (props) => (
  <svg {...props} fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
  </svg>
)

const FolderIcon = (props) => (
  <svg {...props} fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
  </svg>
)

const ServerIcon = (props) => (
  <svg {...props} fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z" />
  </svg>
)

const ExclamationTriangleIcon = (props) => (
  <svg {...props} fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
  </svg>
)

const StatCard = ({ title, value, icon: Icon, colorClass }) => (
  <div className="rounded-xl border border-subtle bg-[#111827] p-5">
    <div className="flex items-start justify-between">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">{title}</p>
        <p className="mt-2 text-3xl font-bold text-white">{value}</p>
      </div>
      <div className={`rounded-lg p-2 ${colorClass}`}>
        <Icon className="h-6 w-6" />
      </div>
    </div>
  </div>
)

const AdminDashboard = () => {
  const [stats, setStats] = useState(null)
  const [analytics, setAnalytics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get("/admin/stats")
      .then((res) => {
        setStats(res.data)
      })
      .catch((err) => {
        setError(err.response?.data?.error || err.message)
      })
      .finally(() => {
        setLoading(false)
      })

    // Fetch analytics data for failure risk score (non-blocking for admins)
    api.get("/analytics/dashboard")
      .then((res) => {
        setAnalytics(res.data)
      })
      .catch(() => {
        // Non-critical: analytics data is optional for admin view
      })
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-6">
        <h2 className="text-sm font-semibold text-rose-400">Access Denied or Error</h2>
        <p className="mt-1 text-sm text-rose-300">{error}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-indigo-500/20 p-2 text-indigo-400">
          <ShieldCheckIcon className="h-6 w-6" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-white">Platform Administration</h1>
          <p className="text-sm text-slate-400">System-wide metrics and status.</p>
        </div>
      </div>

      {/* Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard 
          title="Total Users" 
          value={stats.total_users} 
          icon={UsersIcon} 
          colorClass="bg-blue-500/10 text-blue-400" 
        />
        <StatCard 
          title="Total Projects" 
          value={stats.total_projects} 
          icon={FolderIcon} 
          colorClass="bg-indigo-500/10 text-indigo-400" 
        />
        <StatCard 
          title="Active Deployments" 
          value={stats.active_deployments} 
          icon={ServerIcon} 
          colorClass="bg-emerald-500/10 text-emerald-400" 
        />
        <StatCard 
          title="Total Deployments" 
          value={stats.total_deployments} 
          icon={ServerIcon} 
          colorClass="bg-slate-500/10 text-slate-400" 
        />
        <StatCard 
          title="Incident Reports" 
          value={stats.total_errors} 
          icon={ExclamationTriangleIcon} 
          colorClass="bg-orange-500/10 text-orange-400" 
        />
        <StatCard
          title="Platform Error Rate"
          value={`${stats.platform_error_rate}%`}
          icon={ExclamationTriangleIcon}
          colorClass="bg-rose-500/10 text-rose-400"
        />
        <StatCard
          title="Failure Risk Score"
          value={`${analytics?.failure_risk_score ?? 0}%`}
          icon={ExclamationTriangleIcon}
          colorClass={
            (analytics?.failure_risk_score ?? 0) > 60
              ? "bg-rose-500/10 text-rose-400"
              : (analytics?.failure_risk_score ?? 0) > 30
              ? "bg-amber-500/10 text-amber-400"
              : "bg-emerald-500/10 text-emerald-400"
          }
        />
      </div>

      <div className="rounded-xl border border-subtle bg-[#111827] p-5">
        <h2 className="text-sm font-semibold text-white mb-2">Machine Learning Subsystem</h2>
        <p className="text-sm text-slate-400">
          {analytics
            ? `The anomaly detection engine analyzed ${analytics.total_projects} project(s) and computed a blended ML risk score of ${analytics.failure_risk_score}%. ${analytics.recommendations?.[0] ?? "All systems operating within normal parameters."}`
            : "The Anomaly Detection and Predictive AI engine is active. It monitors platform health and flags anomalous behavior across deployments and login events."}
        </p>
      </div>
    </div>
  )
}

export default AdminDashboard
