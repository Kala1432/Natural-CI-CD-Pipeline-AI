const Settings = () => {
  return (
    <div className="space-y-6">
      <div className="glow-card p-6">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="mt-2 text-slate-400">Configure notifications, cloud credentials, and platform preferences.</p>
      </div>
      <div className="rounded-3xl bg-slate-950 p-6">
        <p className="text-slate-300">Add your AWS credentials, GitHub token, and webhook settings here.</p>
      </div>
    </div>
  )
}

export default Settings
