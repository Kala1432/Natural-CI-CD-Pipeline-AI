const LogsViewer = () => {
  return (
    <div className="space-y-6">
      <div className="glow-card p-6">
        <h1 className="text-2xl font-semibold">Logs Viewer</h1>
        <p className="mt-2 text-slate-400">Stream workflow logs and inspect failed deployment steps.</p>
      </div>
      <div className="glow-card p-6">
        <pre className="max-h-[420px] overflow-y-auto whitespace-pre-wrap rounded-3xl bg-slate-950 p-5 text-sm text-slate-200">{`[INFO] Checking out repository...
[INFO] Installing dependencies...
[ERROR] pytest failed: ModuleNotFoundError: No module named 'flask'
[WARN] Deployment will roll back due to failed build.`}</pre>
      </div>
    </div>
  )
}

export default LogsViewer
