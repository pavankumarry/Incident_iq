import { useState } from 'react'
import { GitPullRequest, AlertTriangle, CheckCircle, XCircle, Shield, Zap, Code } from 'lucide-react'
import { api } from '../api'

const RISK_CONFIG: Record<string, { color: string; icon: any; label: string }> = {
  low:      { color: 'text-green-400',  icon: CheckCircle,    label: 'LOW' },
  medium:   { color: 'text-yellow-400', icon: AlertTriangle,  label: 'MEDIUM' },
  high:     { color: 'text-orange-400', icon: AlertTriangle,  label: 'HIGH' },
  critical: { color: 'text-red-400',    icon: XCircle,        label: 'CRITICAL' },
}

const REC_CONFIG: Record<string, { color: string; label: string }> = {
  APPROVE:         { color: 'text-green-400',  label: '✅ APPROVE' },
  REQUEST_CHANGES: { color: 'text-red-400',    label: '❌ REQUEST CHANGES' },
  COMMENT:         { color: 'text-yellow-400', label: '💬 COMMENT' },
}

export default function PRReview() {
  const [owner, setOwner]     = useState('pavankumarry')
  const [repo, setRepo]       = useState('incidentiq')
  const [prNum, setPrNum]     = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult]   = useState<any>(null)
  const [error, setError]     = useState('')
  const [showReview, setShowReview] = useState(false)

  const analyze = async () => {
    if (!prNum) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const data = await api.analyzePR({
        repo_owner: owner,
        repo_name: repo,
        pr_number: parseInt(prNum),
      })
      setResult(data)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const risk = result ? RISK_CONFIG[result.risk_level] ?? RISK_CONFIG.medium : null
  const rec  = result ? REC_CONFIG[result.recommendation] ?? REC_CONFIG.COMMENT : null

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white">PR Review</h1>
        <p className="text-gray-500 text-sm mt-0.5">
          AI-powered code review with live OTEL correlation.
          When you push a PR, IncidentIQ automatically reviews it and posts a comment.
        </p>
      </div>

      {/* How it works */}
      <div className="card border-sky-800/30 bg-sky-950/20">
        <h2 className="text-sky-400 text-sm font-semibold mb-3">How it works</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          {[
            { step: '1', icon: GitPullRequest, text: 'You push a PR to GitHub' },
            { step: '2', icon: Code,           text: 'Qwen3 Coder reviews the diff for bugs, security issues, performance problems' },
            { step: '3', icon: Zap,            text: 'DeepSeek V3 validates the risk and correlates with live OTEL metrics' },
            { step: '4', icon: Shield,         text: 'Review comment posted to your PR automatically' },
          ].map(({ step, icon: Icon, text }) => (
            <div key={step} className="flex gap-2">
              <span className="text-sky-500 font-bold flex-shrink-0">{step}.</span>
              <div className="flex flex-col gap-1">
                <Icon size={12} className="text-sky-400" />
                <span className="text-gray-400">{text}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Manual trigger */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4">Analyze a PR manually</h2>
        <div className="flex gap-3 flex-wrap">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Repo Owner</label>
            <input
              value={owner}
              onChange={e => setOwner(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-white w-40 focus:outline-none focus:border-sky-500"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Repo Name</label>
            <input
              value={repo}
              onChange={e => setRepo(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-white w-40 focus:outline-none focus:border-sky-500"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">PR Number</label>
            <input
              value={prNum}
              onChange={e => setPrNum(e.target.value)}
              placeholder="42"
              className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-white w-24 focus:outline-none focus:border-sky-500"
            />
          </div>
          <div className="flex flex-col justify-end">
            <button
              onClick={analyze}
              disabled={loading || !prNum}
              className="bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white px-4 py-1.5 rounded text-sm font-medium transition-colors"
            >
              {loading ? 'Analyzing...' : 'Analyze PR'}
            </button>
          </div>
        </div>
        {error && <p className="text-red-400 text-sm mt-3">{error}</p>}
      </div>

      {/* Result */}
      {result && risk && rec && (
        <div className="space-y-4">
          {/* Summary card */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <GitPullRequest size={18} className="text-sky-400" />
                <span className="font-semibold text-white">PR #{result.pr_number} Analysis</span>
              </div>
              <div className="flex items-center gap-3">
                <span className={`font-bold ${risk.color}`}>
                  <risk.icon size={14} className="inline mr-1" />
                  {risk.label}
                </span>
                <span className={`font-semibold ${rec.color}`}>{rec.label}</span>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
              {[
                { label: 'Confidence',    value: `${(result.confidence * 100).toFixed(0)}%`, color: 'text-white' },
                { label: 'Bugs Found',    value: result.bugs_found,          color: result.bugs_found > 0 ? 'text-red-400' : 'text-green-400' },
                { label: 'Security',      value: result.security_issues,     color: result.security_issues > 0 ? 'text-red-400' : 'text-green-400' },
                { label: 'Performance',   value: result.performance_concerns, color: result.performance_concerns > 0 ? 'text-yellow-400' : 'text-green-400' },
                { label: 'OTEL Affected', value: result.otel_correlation?.affected ? 'YES' : 'NO',
                  color: result.otel_correlation?.affected ? 'text-red-400' : 'text-green-400' },
              ].map(({ label, value, color }) => (
                <div key={label} className="bg-gray-800 rounded p-2">
                  <div className="text-gray-500 text-xs">{label}</div>
                  <div className={`font-bold text-lg ${color}`}>{value}</div>
                </div>
              ))}
            </div>

            {result.otel_correlation?.affected && (
              <div className="mt-3 flex items-start gap-2 text-yellow-400 text-xs bg-yellow-900/20 border border-yellow-800/50 rounded p-2">
                <AlertTriangle size={12} className="flex-shrink-0 mt-0.5" />
                <span><strong>OTEL Alert:</strong> {result.otel_correlation.reason}</span>
              </div>
            )}

            {result.triggered_incident && (
              <div className="mt-3 flex items-center gap-2 text-red-400 text-xs bg-red-900/20 border border-red-800/50 rounded p-2">
                <XCircle size={12} />
                <span>Critical bugs detected — incident workflow triggered automatically</span>
              </div>
            )}

            {result.review_posted_to_github && (
              <div className="mt-3 flex items-center gap-2 text-green-400 text-xs">
                <CheckCircle size={12} />
                <span>Review comment posted to GitHub PR</span>
              </div>
            )}
          </div>

          {/* Review body preview */}
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-300">GitHub Review Comment</h2>
              <button
                onClick={() => setShowReview(!showReview)}
                className="text-xs text-sky-400 hover:text-sky-300"
              >
                {showReview ? 'Hide' : 'Show full review'}
              </button>
            </div>
            {showReview && (
              <pre className="text-xs text-gray-300 bg-gray-800 rounded p-3 overflow-auto max-h-96 whitespace-pre-wrap">
                {result.review_body}
              </pre>
            )}
            {!showReview && (
              <p className="text-gray-500 text-xs">
                {result.review_body?.split('\n').slice(0, 3).join(' · ')}...
              </p>
            )}
          </div>
        </div>
      )}

      {/* Webhook setup info */}
      <div className="card border-gray-700/50">
        <h2 className="text-sm font-semibold text-gray-400 mb-2">Automatic Webhook Setup</h2>
        <p className="text-gray-500 text-xs mb-3">
          To have IncidentIQ automatically review every PR you push:
        </p>
        <div className="space-y-1 text-xs font-mono">
          <div className="bg-gray-800 rounded px-3 py-1.5 text-gray-300">
            # 1. Start ngrok to expose local server
          </div>
          <div className="bg-gray-800 rounded px-3 py-1.5 text-sky-300">ngrok http 8000</div>
          <div className="bg-gray-800 rounded px-3 py-1.5 text-gray-300">
            # 2. Register webhook on your GitHub repo
          </div>
          <div className="bg-gray-800 rounded px-3 py-1.5 text-sky-300">
            python scripts/setup_webhook.py
          </div>
          <div className="bg-gray-800 rounded px-3 py-1.5 text-gray-300">
            # 3. Push any PR — IncidentIQ auto-reviews it
          </div>
        </div>
      </div>
    </div>
  )
}
