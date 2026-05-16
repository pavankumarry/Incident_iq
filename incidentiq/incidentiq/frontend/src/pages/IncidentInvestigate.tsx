import { useState } from 'react'
import { Search, AlertTriangle, CheckCircle, Clock, ChevronDown, ChevronUp } from 'lucide-react'
import { api } from '../api'

const DEMO_TELEMETRY = {
  latency_p99_ms: 8200, latency_p50_ms: 1400,
  error_rate_percent: 3.2, cpu_percent: 45,
  memory_mb: 512, active_db_connections: 98,
  requests_per_second: 340,
}

const DEMO_LOGS = [
  "2026-05-16T10:00:01Z ERROR Connection pool exhausted: timeout waiting for connection",
  "2026-05-16T10:00:02Z WARN  Slow query: SELECT * FROM sessions WHERE user_id=? (4.2s)",
  "2026-05-16T10:00:03Z ERROR Connection pool exhausted: timeout waiting for connection",
  "2026-05-16T10:00:05Z WARN  Redis connection timeout after 5000ms",
  "2026-05-16T10:00:07Z ERROR Payment processing failed: upstream timeout",
]

const DEMO_DEPLOYMENTS = [
  { version: "v2.4.0", timestamp: "2026-05-16T08:30:00Z", author: "alice@company.com", description: "Add session caching layer" },
  { version: "v2.4.1", timestamp: "2026-05-16T09:45:00Z", author: "bob@company.com", description: "Fix session handler exception path" },
]

function Section({ title, children, defaultOpen = true }: any) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="card">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between text-sm font-semibold text-gray-300 mb-0">
        <span>{title}</span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {open && <div className="mt-3">{children}</div>}
    </div>
  )
}

export default function IncidentInvestigate() {
  const [service, setService]       = useState('payment-service')
  const [description, setDesc]      = useState('Payment service API latency spiked to 8.2s p99. Users experiencing checkout timeouts.')
  const [severity, setSeverity]     = useState('p1')
  const [telemetry, setTelemetry]   = useState(JSON.stringify(DEMO_TELEMETRY, null, 2))
  const [logs, setLogs]             = useState(DEMO_LOGS.join('\n'))
  const [deployments, setDeploys]   = useState(JSON.stringify(DEMO_DEPLOYMENTS, null, 2))
  const [loading, setLoading]       = useState(false)
  const [result, setResult]         = useState<any>(null)
  const [error, setError]           = useState('')

  const investigate = async () => {
    setLoading(true); setError(''); setResult(null)
    try {
      const data = await api.investigate({
        service, description, severity,
        telemetry: JSON.parse(telemetry),
        logs: logs.split('\n').filter(Boolean),
        deployment_history: JSON.parse(deployments),
      })
      setResult(data)
    } catch (e: any) { setError(e.message) }
    finally { setLoading(false) }
  }

  const SEVER_COLORS: Record<string, string> = { p0: 'text-red-400', p1: 'text-orange-400', p2: 'text-yellow-400', p3: 'text-green-400' }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-white">Incident Investigation</h1>
        <p className="text-gray-500 text-sm mt-0.5">13-step autonomous RCA · Qwen3 32B reasoning · DeepSeek V3 validation</p>
      </div>

      {/* Input form */}
      <div className="card space-y-4">
        <h2 className="text-sm font-semibold text-gray-300">Incident Details</h2>
        <div className="grid grid-cols-3 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Service</label>
            <input value={service} onChange={e => setService(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-sky-500" />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Severity</label>
            <select value={severity} onChange={e => setSeverity(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-sky-500">
              {['p0','p1','p2','p3'].map(s => <option key={s} value={s}>{s.toUpperCase()}</option>)}
            </select>
          </div>
          <div className="flex flex-col justify-end">
            <button onClick={investigate} disabled={loading}
              className="bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white px-4 py-1.5 rounded text-sm font-medium transition-colors">
              {loading ? '🔍 Investigating...' : '🔍 Investigate'}
            </button>
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">Description</label>
          <textarea value={description} onChange={e => setDesc(e.target.value)} rows={2}
            className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-sky-500 resize-none" />
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Telemetry (JSON)</label>
            <textarea value={telemetry} onChange={e => setTelemetry(e.target.value)} rows={8}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-xs text-gray-300 font-mono focus:outline-none focus:border-sky-500 resize-none" />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Logs</label>
            <textarea value={logs} onChange={e => setLogs(e.target.value)} rows={8}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-xs text-gray-300 font-mono focus:outline-none focus:border-sky-500 resize-none" />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Deployment History (JSON)</label>
            <textarea value={deployments} onChange={e => setDeploys(e.target.value)} rows={8}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-xs text-gray-300 font-mono focus:outline-none focus:border-sky-500 resize-none" />
          </div>
        </div>
      </div>

      {error && <div className="card border-red-800/50 text-red-400 text-sm">{error}</div>}

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* Summary */}
          <div className="card border-sky-800/40">
            <div className="flex items-center justify-between mb-3">
              <div>
                <span className="text-sky-400 font-bold">{result.incident_id}</span>
                <span className="text-gray-500 text-xs ml-2">workflow: {result.workflow_id}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className={`font-bold text-sm ${SEVER_COLORS[result.severity] ?? 'text-gray-400'}`}>{result.severity?.toUpperCase()}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${result.state === 'WorkflowState.COMPLETED' ? 'bg-green-900/50 text-green-400' : 'bg-yellow-900/50 text-yellow-400'}`}>
                  {result.state?.replace('WorkflowState.', '')}
                </span>
              </div>
            </div>
            <div className="grid grid-cols-4 gap-3 text-sm">
              {[
                { label: 'Anomalies', value: result.anomalies_detected, color: result.anomalies_detected > 0 ? 'text-red-400' : 'text-green-400' },
                { label: 'RCA Confidence', value: result.rca?.confidence ? `${(result.rca.confidence*100).toFixed(0)}%` : 'N/A', color: 'text-green-400' },
                { label: 'Similar Incidents', value: result.rca?.similar_incidents ?? 0, color: 'text-sky-400' },
                { label: 'Needs Approval', value: result.requires_human_approval ? 'YES' : 'NO', color: result.requires_human_approval ? 'text-yellow-400' : 'text-green-400' },
              ].map(({ label, value, color }) => (
                <div key={label} className="bg-gray-800 rounded p-2">
                  <div className="text-gray-500 text-xs">{label}</div>
                  <div className={`font-bold text-lg ${color}`}>{value}</div>
                </div>
              ))}
            </div>
          </div>

          {/* RCA */}
          {result.rca && (
            <Section title="🧠 Root Cause Analysis">
              <div className="space-y-3 text-sm">
                <div className="bg-gray-800 rounded p-3">
                  <div className="text-gray-500 text-xs mb-1">Top Hypothesis</div>
                  <div className="text-gray-200">{result.rca.top_hypothesis}</div>
                </div>
                {result.rca.mitigations?.length > 0 && (
                  <div>
                    <div className="text-gray-500 text-xs mb-2">Recommended Mitigations</div>
                    {result.rca.mitigations.map((m: string, i: number) => (
                      <div key={i} className="flex gap-2 text-gray-300 mb-1">
                        <span className="text-sky-400 flex-shrink-0">→</span>{m}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Section>
          )}

          {/* PR */}
          {result.pull_request && (
            <Section title="📦 Generated Pull Request">
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-3">
                  <span className="text-sky-400 font-medium">{result.pull_request.title}</span>
                  <span className="text-gray-500 text-xs">confidence: {result.pull_request.confidence ? `${(result.pull_request.confidence*100).toFixed(0)}%` : 'N/A'}</span>
                </div>
                <div className="text-gray-500 text-xs font-mono">branch: {result.pull_request.branch}</div>
              </div>
            </Section>
          )}

          {/* Reasoning log */}
          <Section title="📋 Reasoning Log" defaultOpen={false}>
            <div className="space-y-1">
              {result.reasoning_log?.map((entry: string, i: number) => (
                <div key={i} className="text-xs font-mono text-gray-400 flex gap-2">
                  <span className="text-gray-600 flex-shrink-0">{String(i+1).padStart(2,'0')}</span>
                  <span className={
                    entry.includes('[ObservabilityAgent]') ? 'text-blue-400' :
                    entry.includes('[RCAAgent]') ? 'text-purple-400' :
                    entry.includes('[CodeAgent]') ? 'text-emerald-400' :
                    entry.includes('[GuardrailAgent]') ? 'text-yellow-400' :
                    entry.includes('[KnowledgeAgent]') ? 'text-sky-400' :
                    'text-gray-400'
                  }>{entry}</span>
                </div>
              ))}
            </div>
          </Section>
        </div>
      )}
    </div>
  )
}
