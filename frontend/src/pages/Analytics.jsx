import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from "recharts"

const data = [
  { name: "Mon", success: 95, failures: 5 },
  { name: "Tue", success: 92, failures: 8 },
  { name: "Wed", success: 90, failures: 10 },
  { name: "Thu", success: 94, failures: 6 },
  { name: "Fri", success: 96, failures: 4 },
]

const Analytics = () => {
  return (
    <div className="space-y-6">
      <div className="glow-card p-6">
        <h1 className="text-2xl font-semibold">Analytics Dashboard</h1>
        <p className="mt-2 text-slate-400">AI analytics and pipeline performance metrics for your repos.</p>
      </div>
      <div className="glow-card p-6">
        <h2 className="text-xl font-semibold">Pipeline success trend</h2>
        <div className="mt-6 h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="name" stroke="#94a3b8" />
              <YAxis stroke="#94a3b8" />
              <Tooltip contentStyle={{ backgroundColor: "#111827", border: "1px solid #334155" }} />
              <Line type="monotone" dataKey="success" stroke="#6366f1" strokeWidth={3} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}

export default Analytics
