import { useEffect, useMemo, useState } from "react"
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from "recharts"
import api from "../api"

// Compute linear-regression slope over a numeric series.
const computeSlope = (values) => {
  if (!values || values.length < 2) return 0
  const n = values.length
  const xs = values.map((_, i) => i)
  const xMean = (n - 1) / 2
  const yMean = values.reduce((a, b) => a + b, 0) / n
  let num = 0
  let den = 0
  for (let i = 0; i < n; i++) {
    num += (xs[i] - xMean) * (values[i] - yMean)
    den += (xs[i] - xMean) ** 2
  }
  return den === 0 ? 0 : num / den
}

const Analytics = () => {
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get("/analytics/dashboard")
      .then((res) => {
        setMetrics(res.data)
      })
      .catch((err) => {
        setError(err.message)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  const trend = useMemo(() => {
    const history = metrics?.pipeline_history || []
    if (history.length === 0) {
      return { data: [], slope: 0, totalSuccess: 0, totalFailure: 0 }
    }
    const data = history.map((h) => ({
      name: h.name || h.date,
      success: h.success,
      failures: h.failure,
    }))
    const totals = data.reduce(
      (acc, d) => ({
        success: acc.success + d.success,
        failure: acc.failure + d.failures,
      }),
      { success: 0, failure: 0 }
    )
    const slope = computeSlope(data.map((d) => d.success))
    return { data, slope, totalSuccess: totals.success, totalFailure: totals.failure }
  }, [metrics])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-6 text-sm text-rose-400">
        Failed to load analytics: {error}
      </div>
    )
  }

  const successRate = metrics?.success_rate || 0
  const failureRisk = metrics?.failure_risk_score || 0
  const totalRuns = trend.totalSuccess + trend.totalFailure
  const computedRate = totalRuns > 0
    ? Math.round((trend.totalSuccess / totalRuns) * 1000) / 10
    : successRate
  const trendDown = trend.slope < -0.05

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-white">Analytics Dashboard</h1>
        <p className="mt-0.5 text-sm text-slate-400">
          AI-driven pipeline metrics and optimization guidance.
        </p>
      </div>

      {/* Metrics Grid */}
      <div className="grid gap-4 sm:grid-cols-3">
        {/* Success Rate */}
        <div className="rounded-xl border border-subtle bg-[#111827] p-5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Pipeline Success Rate</p>
            {trendDown && (
              <span
                title="Success rate is trending down"
                className="rounded-md bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-400"
              >
                Trending ↓
              </span>
            )}
          </div>
          <p className="mt-2 text-3xl font-bold text-emerald-400">
            {computedRate}%
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {totalRuns > 0
              ? `Across ${totalRuns} pipeline events (14 days)`
              : "No pipeline events yet"}
          </p>
        </div>

        {/* Active Repos */}
        <div className="rounded-xl border border-subtle bg-[#111827] p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Active Repositories</p>
          <p className="mt-2 text-3xl font-bold text-white">{metrics?.active_repos || 0}</p>
          <p className="mt-1 text-xs text-slate-500">
            {metrics?.total_projects
              ? `of ${metrics.total_projects} total project(s)`
              : "Connected & monitored"}
          </p>
        </div>

        {/* Failure Risk Score */}
        <div className="rounded-xl border border-subtle bg-[#111827] p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">AI Failure Risk Score</p>
          <p className={`mt-2 text-3xl font-bold ${
            failureRisk > 60 ? "text-rose-400" : failureRisk > 30 ? "text-amber-400" : "text-indigo-400"
          }`}>{failureRisk}%</p>
          <p className="mt-1 text-xs text-slate-500">
            {failureRisk > 60 ? "High risk — review recent failures" : failureRisk > 30 ? "Moderate risk" : "Low risk"}
          </p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Chart */}
        <div className="rounded-xl border border-subtle bg-[#111827] p-5 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-white">Pipeline Success Trend</h2>
            <span className="text-xs text-slate-500">Last 14 days</span>
          </div>
          {trend.data.length === 0 ? (
            <div className="flex h-72 flex-col items-center justify-center text-center">
              <p className="text-sm text-slate-400">No pipeline data yet</p>
              <p className="mt-1 text-xs text-slate-500">
                Analyze a project to start tracking pipeline trends.
              </p>
            </div>
          ) : (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trend.data} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="name" stroke="#94a3b8" />
                  <YAxis allowDecimals={false} stroke="#94a3b8" />
                  <Tooltip contentStyle={{ backgroundColor: "#111827", border: "1px solid #334155" }} />
                  <Line type="monotone" dataKey="success" name="Successful Runs" stroke="#10b981" strokeWidth={3} dot={{ fill: "#10b981", r: 4 }} />
                  <Line type="monotone" dataKey="failures" name="Failed Runs" stroke="#f43f5e" strokeWidth={2} dot={{ fill: "#f43f5e", r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Recommendations */}
        <div className="rounded-xl border border-subtle bg-[#111827] p-5">
          <h2 className="text-base font-semibold text-white mb-4">AI Recommendations</h2>
          <ul className="space-y-3">
            {(metrics?.recommendations || []).map((rec, idx) => (
              <li key={idx} className="flex items-start gap-2.5 text-sm text-slate-300">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-500/10 text-indigo-400 text-xs">
                  {idx + 1}
                </span>
                <span className="leading-snug">{rec}</span>
              </li>
            ))}
            {(!metrics?.recommendations || metrics.recommendations.length === 0) && (
              <p className="text-sm text-slate-500">No suggestions at this time.</p>
            )}
          </ul>
        </div>
      </div>
    </div>
  )
}

export default Analytics
