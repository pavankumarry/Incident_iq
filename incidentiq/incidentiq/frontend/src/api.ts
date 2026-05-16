const BASE = '/api'

export async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`${res.status}: ${err}`)
  }
  return res.json()
}

export async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status}`)
  return res.json()
}

// ── API calls ─────────────────────────────────────────────────────────────────

export const api = {
  health: () => get<any>('/health'),
  config: () => get<any>('/config'),

  // Telemetry
  analyzeTelemetry: (data: any) => post<any>('/telemetry/analyze', data),
  getServiceOtel: (service: string) => get<any>(`/pr/otel/${service}`),

  // Incident investigation
  investigate: (data: any) => post<any>('/incident/investigate', data),
  runDemo: () => post<any>('/demo/run'),

  // PR review
  analyzePR: (data: { repo_owner: string; repo_name: string; pr_number: number }) =>
    post<any>('/pr/analyze', data),

  // Copilot
  startCopilot: (params: { incident_id: string; service: string; severity: string; description: string }) =>
    post<any>(`/copilot/start?incident_id=${params.incident_id}&service=${params.service}&severity=${params.severity}&description=${encodeURIComponent(params.description)}`),
  copilotUpdate: (data: any) => post<any>('/copilot/update', data),
  copilotSummary: (id: string) => get<any>(`/copilot/${id}/summary`),
  generatePostmortem: (id: string) => post<any>(`/copilot/${id}/postmortem`),
  closeIncident: (id: string) => post<any>(`/copilot/${id}/close`),

  // Approval
  submitApproval: (data: any) => post<any>('/approval', data),
}
