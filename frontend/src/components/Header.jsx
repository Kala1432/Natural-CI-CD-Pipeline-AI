import { Link } from "react-router-dom"

const Header = () => {
  return (
    <header className="border-b border-slate-800 bg-[#060b18]/80 px-6 py-4 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
        <Link to="/" className="text-xl font-semibold text-white">Pipeline.sh</Link>
        <div className="flex items-center gap-3 text-slate-300">
          <span className="rounded-full bg-slate-900 px-3 py-2 text-sm">Dark</span>
          <button className="rounded-full border border-slate-700 px-3 py-2 text-sm">GitHub</button>
        </div>
      </div>
    </header>
  )
}

export default Header
