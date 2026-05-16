import { useEffect, useState } from 'react'
import { Activity, AlertTriangle, CheckCircle, Clock, Cpu, Database, Zap } from 'lucide-react'
import { api } from '../api'

const SERVICES = ['payment-service', 'order-service', 'user-service', 'auth-service', 'inventory-service']

function MetricCard({ label, value, unit, status }: any) {
  const color = status === 'ok' ? 'text-green-400' : status === 'warn' ? 'text-yellow-400' : 'text-red-400'
  return (
    <div className="card flex flex-col gap-1">
      <span className="text-gray-500 text-xs">{label}</span>
      <span className={`text-2xl font-bold ${color}`}>{value}<span className="text-sm font-normal text-gray-500 ml-1">{unit}</span></span>
    </div>
  )
}

function ServiceRow({ service }: { service: string }) {
  const [snap, setSnap] = useState<any>(null)

  useEffect(() => {
    api.getServiceOtel(service).then(setSnap).catch(() => {})
    const t = setInterval(() => api.getServiceOtel(service).then(setSnap).catch(() => {}), 10000)
    return () => clearInterval(t)
  }, [service])

  if (!snap) return (
    <div className="card animate-pulse flex items-center gap-3">
      <div className="w-2 h-2 bg-gray-700 rounded-full" />
      <span className="text-gray-600 text-sm">{service}</span>
    </div>
  )

  const healthy = snap.healthy
  const latencyStatus = snap.latency_p99_ms > 500 ? 'critical' : snap.latency_p99_ms > 300 ? 'warn' : 'ok'
  const errorStatus = snap.error_rate_percent > 2 ? 'critical' : snap.error_rate_percent > 0.5 ? 'warn' : 'ok'

  return (
    <div className={`card flex items-center gap-4 ${!healthy ? 'border-red-800/50' : ''}`}>
      <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${healthy ? 'bg-green-400' : 'bg-red-400 animate-pulse'}`} />
      <span className="text-sm font-medium w-44 truncate">{service}</span>

      <div className="flex gap-6 flex-1 text-xs">
        <div>
          <span className="text-gray-500">p99 </span>
          <span className={latencyStatus === 'ok' ? 'text-green-400' : latencyStatus === 'warn' ? 'text-yellow-400' : 'text-red-400'}>
            {snap.latency_p99_ms}ms
          </span>
        </div>
        <div>
          <span className="text-gray-500">errors </span>
          <span className={errorStatus === 'ok' ? 'text-green-400' : errorStatus === 'warn' ? 'text-yellow-400' : 'text-red-400'}>
            {snap.error_rate_percent}%
          </span>
        </div>
        <div>
          <span className="text-gray-500">cpu </span>
          <span className={snap.cpu_percent > 80 ? 'text-red-400' : 'text-gray-300'}>{snap.cpu_percent}%</span>
        </div>
        <div>
          <span className="text-gray-500">db conn </span>
          <span className={snap.active_db_connections > 80 ? 'text-red-400' : 'text-gray-300'}>{snap.active_db_connections}</span>
        </div>
        <div>
          <span className="text-gray-500">version </span>
          <span className="text-gray-400">{snap.current_version || 'N/A'}</span>
        </div>
      </div>

      {snap.recent_errors?.length > 0 && (
        <div className="flex items-center gap-1 text-yellow-400 text-xs">
          <AlertTriangle size={12} />
          <span>{snap.recent_errors.length} recent errors</span>
        </div>
      )}
    </div>
  )
}

export default function Dashboard() {
  const [health, setHealth] = useState<any>(null)
  const [demoRunning, setDemoRunning] = useState(false)
  const [demoResult, setDemoResult] = useState<any>(null)

  useEffect(() => {
    api.health().then(setHealth).catch(() => {})
  }, [])

  const runDemo = async () => {
    setDemoRunning(true)
    setDemoResult(null)
    try {
      const result = await api.runDemo()
      setDemoResult(result)
    } catch (e: any) {
      setDemoResult({ error: e.message })
    } finally {
      setDemoRunning(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">System Overview</h1>
          <p className="text-gray-500 text-sm mt-0.5">Live telemetry · OTEL correlation · AI monitoring</p>
        </div>
        <button
          onClick={runDemo}
          disabled={demoRunning}
          className="flex items-center gap-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <Zap size={14} />
          {demoRunning ? 'Running Demo...' : 'Run Demo Scenario'}
        </button>
      </div>

      {/* Status bar */}
      {health && (
        <div className="card flex items-center gap-6 text-sm">
          <div className="flex items-center gap-2">
            <CheckCircle size={14} className="text-green-400" />
            <span className="text-green-400">API Online</span>
          </div>
          <div className="text-gray-500">Region: <span className="text-gray-300">{health.bedrock_region}</span></div>
          <div className="text-gray-500">Mode: <span className="text-yellow-400">{health.advisory_only_mode ? 'Advisory Only' : 'Autonomous'}</span></div>
          <div className="text-gray-500">Env: <span className="text-gray-300">{health.environment}</span></div>
        </div>
      )}

      {/* Model stack */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-400 mb-3">Active Model Stack</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { priority: 'P1', model: 'Qwen3 32B', role: 'Primary Reasoning / RCA', color: 'sky' },
            { priority: 'P2', model: 'DeepSeek V3', role: 'Deep Analysis / Validation', color: 'violet' },
            { priority: 'P3', model: 'Qwen3 Coder', role: 'Code Review / PR Gen', color: 'emerald' },
            { priority: 'P4', model: 'Kimi K2', role: 'Fast ChatOps / Summaries', color: 'amber' },
          ].map(({ priority, model, role, color }) => (
            <div key={priority} className="bg-gray-800/50 rounded-lg p-3 border border-gray-700/50">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs font-bold text-${color}-400`}>{priority}</span>
                <span className="w-1.5 h-1.5 bg-green-400 rounded-full" />
              </div>
              <div className="text-sm font-medium text-white">{model}</div>
              <div className="text-xs text-gray-500 mt-0.5">{role}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Service health */}
      <div>
        <h2 className="text-sm font-semibold text-gray-400 mb-3 flex items-center gap-2">
          <Activity size={14} />
          Live Service Health
          <span className="text-gray-600 font-normal">(refreshes every 10s)</span>
        </h2>
        <div className="space-y-2">
          {SERVICES.map(s => <ServiceRow key={s} service={s} />)}
        </div>
      </div>

      {/* Demo result */}
      {demoResult && (
        <div className="card border-sky-800/50">
          <h2 className="text-sm font-semibold text-sky-400 mb-3 flex items-center gap-2">
            <Zap size={14} />
            Demo Result — {demoResult.incident_id}
          </h2>
          {demoResult.error ? (
            <p className="text-red-400 text-sm">{demoResult.error}</p>
          ) : (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-gray-800 rounded p-2">
                  <div className="text-gray-500 text-xs">Anomalies</div>
                  <div className="text-white font-bold text-lg">{demoResult.anomalies_detected}</div>
                </div>
                <div className="bg-gray-800 rounded p-2">
                  <div className="text-gray-500 text-xs">RCA Confidence</div>
                  <div className="text-green-400 font-bold text-lg">
                    {demoResult.rca?.confidence ? `${(demoResult.rca.confidence * 100).toFixed(0)}%` : 'N/A'}
                  </div>
                </div>
                <div className="bg-gray-800 rounded p-2">
                  <div className="text-gray-500 text-xs">Similar Incidents</div>
                  <div className="text-white font-bold text-lg">{demoResult.rca?.similar_incidents ?? 0}</div>
                </div>
              </div>
              {demoResult.rca?.top_hypothesis && (
                <div className="bg-gray-800 rounded p-3">
                  <div className="text-gray-500 text-xs mb-1">Top Hypothesis</div>
                  <div className="text-gray-200">{demoResult.rca.top_hypothesis}</div>
                </div>
              )}
              {demoResult.pull_request && (
                <div className="bg-gray-800 rounded p-3">
                  <div className="text-gray-500 text-xs mb-1">Generated PR</div>
                  <div className="text-sky-400">{demoResult.pull_request.title}</div>
                  <div className="text-gray-500 text-xs mt-1">Branch: {demoResult.pull_request.branch}</div>
                </div>
              )}
              {demoResult.requires_human_approval && (
                <div className="flex items-center gap-2 text-yellow-400 text-xs bg-yellow-900/20 border border-yellow-800/50 rounded p-2">
                  <AlertTriangle size={12} />
                  Human approval required before deployment
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
