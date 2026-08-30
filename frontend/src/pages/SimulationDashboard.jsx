import { useEffect, useRef, useState } from "react"
import { useNavigate, useParams, Link } from "react-router-dom"
import api from "../api"

const STATUS_UI = {
  running: { label: "Running...", color: "text-blue-400 bg-blue-500/10 border-blue-500/20", icon: "⏳" },
  failed_as_expected: { label: "Chaos Successful", color: "text-yellow-400 bg-yellow-500/10 border-yellow-500/20", icon: "💥" },
  ai_fixed: { label: "AI Fixed", color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20", icon: "✨" },
  error: { label: "Simulation Error", color: "text-rose-400 bg-rose-500/10 border-rose-500/20", icon: "❌" },
}

const SimulationDashboard = () => {
  const { id } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState(null)
  const [simulations, setSimulations] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  
  const [showTriggerForm, setShowTriggerForm] = useState(false)
  const [triggerType, setTriggerType] = useState("syntax_error")
  const [triggering, setTriggering] = useState(false)
  
  const [selectedSimId, setSelectedSimId] = useState(null)
  const pollRef = useRef(null)

  const load = async () => {
    try {
      const projRes = await api.get(`/projects/${id}`)
      setProject(projRes.data.project)
      const simRes = await api.get(`/projects/${id}/simulations`)
      setSimulations(simRes.data.simulations || [])
      
      // Auto-select latest simulation if none selected
      if (!selectedSimId && simRes.data.simulations?.length > 0) {
        setSelectedSimId(simRes.data.simulations[0].id)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    pollRef.current = setInterval(load, 5000)
    return () => clearInterval(pollRef.current)
  }, [id, selectedSimId])

  const handleTrigger = async (e) => {
    e.preventDefault()
    setTriggering(true)
    try {
      const res = await api.post(`/projects/${id}/simulate`, { error_type: triggerType })
      setSimulations([res.data.simulation, ...simulations])
      setSelectedSimId(res.data.simulation.id)
      setShowTriggerForm(false)
    } catch (err) {
      alert("Failed to trigger simulation: " + (err.response?.data?.error || err.message))
    } finally {
      setTriggering(false)
    }
  }

  if (loading && !project) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-6 text-sm text-rose-400">
        Failed to load simulations: {error}
      </div>
    )
  }

  const selectedSim = simulations.find(s => s.id === selectedSimId)

  return (
    <div className="flex h-full flex-col space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm text-slate-500 mb-1">
            <Link to="/projects" className="hover:text-slate-300 transition-colors">Projects</Link>
            <span>/</span>
            <Link to={`/projects/${id}`} className="hover:text-slate-300 transition-colors">{project.repo_name}</Link>
            <span>/</span>
            <span className="text-slate-300">Simulations</span>
          </div>
          <h1 className="text-xl font-semibold text-white">Chaos Simulations</h1>
        </div>
        <button
          onClick={() => setShowTriggerForm(!showTriggerForm)}
          className="inline-flex items-center gap-2 rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-500 transition-colors"
        >
          🔥 Inject Error
        </button>
      </div>

      {showTriggerForm && (
        <form onSubmit={handleTrigger} className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-6 backdrop-blur-sm">
          <h2 className="text-base font-semibold text-white mb-4">Start new Chaos Simulation</h2>
          <div className="flex gap-4 items-end">
            <div className="flex-1">
              <label className="block text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">Error Type</label>
              <select
                value={triggerType}
                onChange={(e) => setTriggerType(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-[#1e293b] px-4 py-2.5 text-sm text-white focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
              >
                <option value="syntax_error">Syntax Error</option>
                <option value="missing_import">Missing Import</option>
                <option value="failing_test">Failing Test</option>
              </select>
            </div>
            <button
              type="submit"
              disabled={triggering}
              className="rounded-lg bg-rose-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-rose-500 disabled:opacity-50"
            >
              {triggering ? "Starting..." : "Trigger Simulation"}
            </button>
          </div>
        </form>
      )}

      {/* Main Grid */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-6 overflow-hidden">
        {/* Sidebar: List of Simulations */}
        <div className="col-span-1 border border-subtle bg-[#111827] rounded-xl overflow-y-auto">
          <div className="sticky top-0 bg-[#111827]/95 backdrop-blur z-10 border-b border-subtle px-4 py-3">
            <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">History</h3>
          </div>
          {simulations.length === 0 ? (
            <div className="p-6 text-center text-sm text-slate-500">No simulations run yet.</div>
          ) : (
            <div className="divide-y divide-white/5">
              {simulations.map(sim => {
                const ui = STATUS_UI[sim.status] || { label: sim.status, color: "text-slate-400 bg-white/5 border-white/10", icon: "•" }
                return (
                  <button
                    key={sim.id}
                    onClick={() => setSelectedSimId(sim.id)}
                    className={`w-full text-left p-4 transition-colors hover:bg-white/5 ${selectedSimId === sim.id ? "bg-white/5 border-l-2 border-l-indigo-500" : ""}`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <span className="font-mono text-xs text-slate-300">#{sim.id} - {sim.injected_file}</span>
                      <span className={`text-xs px-2 py-0.5 rounded border ${ui.color}`}>
                        {ui.icon} {ui.label}
                      </span>
                    </div>
                    <div className="text-sm text-white font-medium mb-1">
                      {sim.injected_error_type.replace("_", " ")}
                    </div>
                    <div className="text-xs text-slate-500">
                      {new Date(sim.created_at).toLocaleString()}
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Main Panel: Simulation Details */}
        <div className="col-span-2 border border-subtle bg-[#111827] rounded-xl flex flex-col overflow-hidden">
          {!selectedSim ? (
            <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
              Select a simulation to view details
            </div>
          ) : (
            <>
              {/* Top: Status & Diagnosis */}
              <div className="border-b border-subtle p-5 bg-gradient-to-br from-indigo-500/5 to-transparent">
                <h3 className="text-lg font-semibold text-white mb-4">
                  Simulation #{selectedSim.id}: {selectedSim.injected_error_type.replace("_", " ")}
                </h3>
                
                {selectedSim.ai_diagnosis ? (
                  <div className="rounded-lg bg-indigo-500/10 border border-indigo-500/20 p-4">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-indigo-400 mb-2">🤖 AI Diagnosis</h4>
                    <p className="text-sm text-indigo-100 whitespace-pre-wrap">{selectedSim.ai_diagnosis}</p>
                  </div>
                ) : (
                  <div className="rounded-lg bg-white/5 border border-white/10 p-4 flex items-center gap-3">
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-500 border-t-transparent" />
                    <span className="text-sm text-slate-400">Waiting for AI diagnosis...</span>
                  </div>
                )}
              </div>

              {/* Bottom: Logs & Fix Tabs */}
              <div className="flex-1 flex flex-col min-h-[400px]">
                <div className="flex items-center gap-4 border-b border-subtle px-4">
                  <div className="px-2 py-3 border-b-2 border-indigo-500 text-sm font-medium text-white">
                    Logs & Diff
                  </div>
                </div>
                
                <div className="flex-1 overflow-y-auto p-4 space-y-6">
                  {/* CI Logs */}
                  {selectedSim.pipeline_log && (
                    <div>
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Failed CI Output</h4>
                      <pre className="text-xs bg-slate-950 p-4 rounded-xl text-red-400 overflow-x-auto border border-red-500/10 whitespace-pre-wrap font-mono">
                        {selectedSim.pipeline_log}
                      </pre>
                    </div>
                  )}

                  {/* AI Fix Diff */}
                  {selectedSim.ai_fix_diff && (
                    <div>
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-emerald-500 mb-2">Applied AI Fix</h4>
                      <pre className="text-xs bg-slate-950 p-4 rounded-xl text-emerald-400 overflow-x-auto border border-emerald-500/10 whitespace-pre-wrap font-mono">
                        {selectedSim.ai_fix_diff}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default SimulationDashboard
