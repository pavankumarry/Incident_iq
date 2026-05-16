import { useState } from 'react'
import { Terminal, Play, RefreshCw } from 'lucide-react'
import { api } from '../api'

const AGENT_COLORS: Record<string, string> = {
  '[ObservabilityAgent]': 'text-blue-400',
  '[RCAAgent]':           'text-purple-400',
  '[CodeAgent]':          'text-emerald-400',
  '[GuardrailAgent]':     'text-yellow-400',
  '[KnowledgeAgent]':     'text-sky-400',
  '[Copilot]':            'text-pink-400',
  'Step ':                'text-gray-300',
  'Starting':             'text-white',
  'Workflow':             'text-white',
}

function colorLine(line: string): string {
  for (const [key, cls] of Object.entries(AGENT_COLORS)) {
    if (line.includes(key)) return cls
  }
  return 'text-gray-500'
}

export default function ReasoningLog() {
  const [running, setRunning]   = useState(false)
  const [log, setLog]           = useState<string[]>([])
  const [result, setResult]     = useState<any>(null)
  const [error, setError]       = useState('')

  const runDemo = async () => {
    setRunning(true); setLog([]); setResult(null); setError('')
    // Stream log lines as they come in
    const lines: string[] = []
    const addLine = (line: string) => {
      lines.push(line)
      setLog([...lines])
    }

    addLine('▶  Starting IncidentIQ demo scenario...')
    addLine('   Service: payment-service | Severity: P1')
    addLine('')

    try {
      const data = await api.runDemo()
      setResult(data)

      // Replay the reasoning log with a small delay for visual effect
      if (data.reasoning_log) {
        for (const entry of data.reasoning_log) {
          addLine(entry)
          await new Promise(r => setTimeout(r, 60))
        }
      }
      addLine('')
      addLine(`✅  Workflow ${data.workflow_id} completed — state: ${data.state?.replace('WorkflowState.', '')}`)
    } catch (e: any) {
      setError(e.message)
      addLine(`❌  Error: ${e.message}`)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Reasoning Log</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            Every autonomous action is explained. Full audit trail of agent decisions.
          </p>
        </div>
        <button onClick={runDemo} disabled={running}
          className="flex items-center gap-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
          {running ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
          {running ? 'Running...' : 'Run Demo & Watch'}
        </button>
      </div>

      {/* Legend */}
      <div className="card flex flex-wrap gap-4 text-xs">
        {[
          { label: 'ObservabilityAgent', color: 'text-blue-400' },
          { label: 'RCAAgent',           color: 'text-purple-400' },
          { label: 'CodeAgent',          color: 'text-emerald-400' },
          { label: 'GuardrailAgent',     color: 'text-yellow-400' },
          { label: 'KnowledgeAgent',     color: 'text-sky-400' },
          { label: 'System',             color: 'text-gray-300' },
        ].map(({ label, color }) => (
          <div key={label} className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full bg-current ${color}`} />
            <span className={color}>{label}</span>
          </div>
        ))}
      </div>

      {/* Terminal */}
      <div className="card bg-gray-950 border-gray-800 min-h-96">
        <div className="flex items-center gap-2 mb-3 pb-2 border-b border-gray-800">
          <Terminal size={14} className="text-gray-500" />
          <span className="text-gray-500 text-xs">incidentiq reasoning log</span>
          {running && <span className="text-green-400 text-xs animate-pulse ml-auto">● live</span>}
        </div>
        <div className="font-mono text-xs space-y-0.5 max-h-[600px] overflow-y-auto">
          {log.length === 0 && !running && (
            <div className="text-gray-600">
              Click "Run Demo & Watch" to see the full 13-step reasoning chain live.
            </div>
          )}
          {log.map((line, i) => (
            <div key={i} className={`leading-5 ${colorLine(line)}`}>
              {line || <br />}
            </div>
          ))}
          {running && <span className="text-green-400 animate-pulse">█</span>}
        </div>
      </div>

      {/* Result summary */}
      {result && !running && (
        <div className="card border-sky-800/40">
          <h2 className="text-sm font-semibold text-sky-400 mb-3">Workflow Summary</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            {[
              { label: 'Incident ID',      value: result.incident_id },
              { label: 'Anomalies',        value: result.anomalies_detected },
              { label: 'RCA Confidence',   value: result.rca?.confidence ? `${(result.rca.confidence*100).toFixed(0)}%` : 'N/A' },
              { label: 'Similar Incidents',value: result.rca?.similar_incidents ?? 0 },
            ].map(({ label, value }) => (
              <div key={label} className="bg-gray-800 rounded p-2">
                <div className="text-gray-500 text-xs">{label}</div>
                <div className="text-white font-bold">{value}</div>
              </div>
            ))}
          </div>
          {result.rca?.top_hypothesis && (
            <div className="mt-3 bg-gray-800 rounded p-3 text-sm text-gray-200">
              <span className="text-gray-500 text-xs block mb-1">Top Hypothesis</span>
              {result.rca.top_hypothesis}
            </div>
          )}
          {result.pull_request && (
            <div className="mt-3 bg-gray-800 rounded p-3 text-sm">
              <span className="text-gray-500 text-xs block mb-1">Generated PR</span>
              <span className="text-sky-400">{result.pull_request.title}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
