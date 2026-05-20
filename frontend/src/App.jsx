import { Routes, Route, Navigate } from "react-router-dom"
import LandingPage from "./pages/LandingPage"
import LoginPage from "./pages/LoginPage"
import RegisterPage from "./pages/RegisterPage"
import Dashboard from "./pages/Dashboard"
import ReposPage from "./pages/ReposPage"
import WorkflowBuilder from "./pages/WorkflowBuilder"
import DeploymentMonitor from "./pages/DeploymentMonitor"
import LogsViewer from "./pages/LogsViewer"
import Analytics from "./pages/Analytics"
import ErrorInsights from "./pages/ErrorInsights"
import Profile from "./pages/Profile"
import Settings from "./pages/Settings"
import Sidebar from "./components/Sidebar"
import Header from "./components/Header"

const App = () => {
  return (
    <div className="min-h-screen bg-bg text-white">
      <Header />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 p-6">
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/repos" element={<ReposPage />} />
            <Route path="/workflow" element={<WorkflowBuilder />} />
            <Route path="/deployments" element={<DeploymentMonitor />} />
            <Route path="/logs" element={<LogsViewer />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/errors" element={<ErrorInsights />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

export default App
