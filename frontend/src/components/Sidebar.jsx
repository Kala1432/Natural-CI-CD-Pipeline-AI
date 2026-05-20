import { NavLink } from "react-router-dom"

const links = [
  { label: "Dashboard", to: "/dashboard" },
  { label: "Repositories", to: "/repos" },
  { label: "Workflow", to: "/workflow" },
  { label: "Deployments", to: "/deployments" },
  { label: "Logs", to: "/logs" },
  { label: "Analytics", to: "/analytics" },
  { label: "Errors", to: "/errors" },
  { label: "Profile", to: "/profile" },
  { label: "Settings", to: "/settings" },
]

const Sidebar = () => {
  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-950 px-4 py-6 hidden lg:block">
      <div className="mb-10 text-center">
        <div className="text-xl font-bold text-white">Pipeline.sh</div>
        <p className="text-sm text-slate-400">AI DevOps</p>
      </div>
      <nav className="space-y-2">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) =>
              `block rounded-3xl px-4 py-3 text-sm ${isActive ? "bg-accent text-white" : "text-slate-300 hover:bg-slate-800"}`
            }
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}

export default Sidebar
