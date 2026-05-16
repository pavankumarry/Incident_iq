import { useState, useRef, useEffect } from 'react'
import { Zap, Send, AlertTriangle, CheckCircle, MessageSquare, Activity } from 'lucide-react'
import { api } from '../api'

interface Message {
  id: number
  type: 'user' | 'system' | 'interjection' | 'summary'
  text: string
  confidence?: number
  evidence?: string[]
  command?: string
  priority?: string
  timestamp: string
}

let msgId = 0

export default function LiveCopilot() {
  const [incidentId, setIncidentId]   = useState('')
  const [service, setService]         = useState('payment-service')
  const [severity, setSeverity]       = useState('p1')
  const [description, setDesc]        = useState('Payment service latency spike')
  const [started, setStarted]         = useState(false)
  const [messages, setMessages]       = useState<Message[]>([])
  const [input, setInput]             = useState('')
  const [sending, setSending]         = useState(false)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [postmortemLoading, setPostmortemLoading] = useState(false)
  const [postmortem, setPostmortem]   = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const addMsg = (msg: Omit<Message, 'id' | 'timestamp'>) => {
    setMessages(prev => [...prev, { ...msg, id: ++msgId, timestamp: new Date().toLocaleTimeString() }])
  }

  const startIncident = async () => {
    const id = `INC-${Date.now()}`
    try {
      await api.startCopilot({ incident_id: id, service, severity, description })
      setIncidentId(id)
      setStarted(true)
      addMsg({ type: 'system', text: `🚨 Incident ${id} started. Copilot is watching. Send updates as you investigate.` })
      addMsg({ type: 'system', text: `Service: ${service} | Severity: ${severity.toUpperCase()} | ${description}` })
    } catch (e: any) {
      addMsg({ type: 'system', text: `Failed to start: ${e.message}` })
    }
  }

  const sendUpdate = async (updateType: string = 'slack_message') => {
    if (!input.trim() || !incidentId) return
    const text = input.trim()
    setInput('')
    addMsg({ type: 'user', text })
    setSending(true)
    try {
      const result = await api.copilotUpdate({
        incident_id: incidentId,
        update_type: updateType,
        content: text,
      })
      if (result.interjection) {
        const inj = result.interjection
        addMsg({
          type: 'interjection',
          text: inj.message,
          confidence: inj.confidence,
          evidence: inj.evidence,
          command: inj.suggested_command,
          priority: inj.priority,
        })
      }
    } catch (e: any) {
      addMsg({ type: 'system', text: `Error: ${e.message}` })
    } finally {
      setSending(false)
    }
  }

  const getSummary = async () => {
    setSummaryLoading(true)
    try {
      const result = await api.copilotSummary(incidentId)
      addMsg({ type: 'summary', text: result.summary })
    } catch (e: any) {
      addMsg({ type: 'system', text: `Summary failed: ${e.message}` })
    } finally {
      setSummaryLoading(false) }
  }

  const generatePostmortem = async () => {
    setPostmortemLoading(true)
    try {
      const result = await api.generatePostmortem(incidentId)
      setPostmortem(result.postmortem)
    } catch (e: any) {
      addMsg({ type: 'system', text: `Postmortem failed: ${e.message}` })
    } finally {
      setPostmortemLoading(false) }
  }

  const PRIORITY_COLOR: Record<string, string> = {
    critical: 'border-red-700 bg-red-950/40',
    high:     'border-orange-700 bg-orange-950/40',
    medium:   'border-yellow-700 bg-yellow-950/40',
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-white">Live Incident Copilot</h1>
        <p className="text-gray-500 text-sm mt-0.5">
          Real-time AI second pair of eyes. Send updates as you investigate — the copilot interjects when it has high-confidence insights.
        </p>
      </div>

      {!started ? (
        <div className="card space-y-4">
          <h2 className="text-sm font-semibold text-gray-300">Start Incident Session</h2>
          <div className="grid grid-cols-2 gap-3">
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
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Initial Description</label>
            <input value={description} onChange={e => setDesc(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-sky-500" />
          </div>
          <button onClick={startIncident}
            className="bg-sky-600 hover:bg-sky-500 text-white px-4 py-2 rounded text-sm font-medium transition-colors flex items-center gap-2">
            <Zap size={14} /> Start Copilot Session
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Status bar */}
          <div className="card flex items-center justify-between py-2">
            <div className="flex items-center gap-3">
              <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
              <span className="text-green-400 text-sm font-medium">{incidentId}</span>
              <span className="text-gray-500 text-xs">{service} · {severity.toUpperCase()}</span>
            </div>
            <div className="flex gap-2">
              <button onClick={getSummary} disabled={summaryLoading}
                className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1 rounded transition-colors disabled:opacity-50">
                {summaryLoading ? 'Loading...' : '📋 Summary'}
              </button>
              <button onClick={generatePostmortem} disabled={postmortemLoading}
                className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1 rounded transition-colors disabled:opacity-50">
                {postmortemLoading ? 'Loading...' : '📄 Postmortem'}
              </button>
            </div>
          </div>

          {/* Chat window */}
          <div className="card h-96 overflow-y-auto space-y-3 flex flex-col">
            {messages.map(msg => (
              <div key={msg.id} className={`text-sm ${msg.type === 'user' ? 'flex justify-end' : ''}`}>
                {msg.type === 'user' && (
                  <div className="bg-sky-900/50 border border-sky-800/50 rounded-lg px-3 py-2 max-w-lg">
                    <div className="text-sky-200">{msg.text}</div>
                    <div className="text-sky-500 text-xs mt-1">{msg.timestamp}</div>
                  </div>
                )}
                {msg.type === 'system' && (
                  <div className="text-gray-500 text-xs flex items-center gap-2">
                    <Activity size={10} />
                    {msg.text}
                  </div>
                )}
                {msg.type === 'summary' && (
                  <div className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2">
                    <div className="text-xs text-gray-500 mb-1 flex items-center gap-1">
                      <MessageSquare size={10} /> Live Summary
                    </div>
                    <div className="text-gray-200">{msg.text}</div>
                  </div>
                )}
                {msg.type === 'interjection' && (
                  <div className={`border rounded-lg px-3 py-2 ${PRIORITY_COLOR[msg.priority ?? 'medium'] ?? 'border-gray-700 bg-gray-800'}`}>
                    <div className="flex items-center gap-2 mb-2">
                      <Zap size={12} className="text-yellow-400" />
                      <span className="text-yellow-400 text-xs font-bold">COPILOT INSIGHT</span>
                      <span className="text-gray-500 text-xs">confidence: {msg.confidence ? `${(msg.confidence*100).toFixed(0)}%` : 'N/A'}</span>
                      <span className="text-gray-600 text-xs ml-auto">{msg.timestamp}</span>
                    </div>
                    <div className="text-gray-200 mb-2">{msg.text}</div>
                    {msg.evidence && msg.evidence.length > 0 && (
                      <div className="text-xs text-gray-500 mb-1">
                        Evidence: {msg.evidence.join(' · ')}
                      </div>
                    )}
                    {msg.command && (
                      <div className="bg-gray-900 rounded px-2 py-1 font-mono text-xs text-green-400 mt-1">
                        $ {msg.command}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="flex gap-2">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendUpdate()}
              placeholder="Type an update (e.g. 'Checked Redis pool — at 95% capacity') and press Enter..."
              className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-sky-500"
            />
            <button onClick={() => sendUpdate('action_taken')} disabled={sending || !input.trim()}
              className="bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white px-3 py-2 rounded text-xs transition-colors">
              Action
            </button>
            <button onClick={() => sendUpdate('slack_message')} disabled={sending || !input.trim()}
              className="bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white px-3 py-2 rounded transition-colors">
              <Send size={14} />
            </button>
          </div>

          <p className="text-gray-600 text-xs">
            Copilot interjects when confidence ≥ 70% · max 1 suggestion per 5 minutes · advisory only
          </p>
        </div>
      )}

      {/* Postmortem */}
      {postmortem && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-3">📄 Auto-Generated Postmortem</h2>
          <pre className="text-xs text-gray-300 whitespace-pre-wrap bg-gray-800 rounded p-3 max-h-96 overflow-y-auto">
            {postmortem}
          </pre>
        </div>
      )}
    </div>
  )
}
