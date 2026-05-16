import { useState } from 'react'
import { Activity, GitPullRequest, Search, Zap, Shield, Terminal } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import PRReview from './pages/PRReview'
import IncidentInvestigate from './pages/IncidentInvestigate'
import LiveCopilot from './pages/LiveCopilot'
import ReasoningLog from './pages/ReasoningLog'

const TABS = [
  { id: 'dashboard',   label: 'Dashboard',    icon: Activity },
  { id: 'pr-review',   label: 'PR Review',    icon: GitPullRequest },
  { id: 'investigate', label: 'Investigate',  icon: Search },
  { id: 'copilot',     label: 'Live Copilot', icon: Zap },
  { id: 'reasoning',   label: 'Reasoning Log',icon: Terminal },
]

export default function App() {
  const [tab, setTab] = useState('dashboard')

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-sky-500 rounded-lg flex items-center justify-center">
              <Shield size={16} className="text-white" />
            </div>
            <div>
              <span className="font-bold text-white text-lg tracking-tight">IncidentIQ</span>
              <span className="text-gray-500 text-xs ml-2">AI Incident Response</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
            <span className="text-green-400 text-xs">Bedrock Connected</span>
          </div>
        </div>

        {/* Tabs */}
        <div className="max-w-7xl mx-auto px-4 flex gap-1 pb-0">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex items-center gap-1.5 px-3 py-2 text-sm rounded-t-lg border-b-2 transition-colors ${
                tab === id
                  ? 'border-sky-500 text-sky-400 bg-gray-900/50'
                  : 'border-transparent text-gray-500 hover:text-gray-300'
              }`}
            >
              <Icon size={14} />
              {label}
            </button>
          ))}
        </div>
      </header>

      {/* Page content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
        {tab === 'dashboard'   && <Dashboard />}
        {tab === 'pr-review'   && <PRReview />}
        {tab === 'investigate' && <IncidentInvestigate />}
        {tab === 'copilot'     && <LiveCopilot />}
        {tab === 'reasoning'   && <ReasoningLog />}
      </main>
    </div>
  )
}
