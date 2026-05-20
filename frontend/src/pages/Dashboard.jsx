import RepoCard from "../components/RepoCard"
import PipelineCard from "../components/PipelineCard"
import ChartCard from "../components/ChartCard"

const Dashboard = () => {
  const repositories = [
    { name: "pipeline-sh", stage: "production", health: "Healthy", status: "Success" },
    { name: "flask-api", stage: "staging", health: "Warning", status: "Failed" },
  ]

  return (
    <div className="space-y-8">
      <div className="grid gap-6 lg:grid-cols-3">
        <ChartCard title="Active Pipelines" value="12" />
        <ChartCard title="Success Rate" value="92%" />
        <ChartCard title="AI Failure Risk" value="8%" />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="glow-card p-6">
          <h2 className="text-xl font-semibold">Repository Activity</h2>
          <div className="mt-6 space-y-4">
            {repositories.map((repo) => (
              <RepoCard key={repo.name} repo={repo} />
            ))}
          </div>
        </div>
        <div className="glow-card p-6">
          <h2 className="text-xl font-semibold">Recent Pipeline Runs</h2>
          <div className="mt-6 space-y-4">
            <PipelineCard title="Build #204" status="Success" environment="prod" />
            <PipelineCard title="Deploy #123" status="Failed" environment="staging" />
          </div>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
