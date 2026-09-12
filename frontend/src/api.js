// Thin API client. All calls go through the Vite dev-server proxy at /api.

const BASE = '/api'
// Optional API key (only needed if the backend has auth enabled).
const API_KEY = import.meta.env.VITE_API_KEY || ''

function headers(extra) {
  const h = { ...(extra || {}) }
  if (API_KEY) h['X-API-Key'] = API_KEY
  return h
}

// EventSource cannot set headers, so the key goes in the query string for SSE.
export function eventsUrl(id) {
  const suffix = API_KEY ? `?api_key=${encodeURIComponent(API_KEY)}` : ''
  return `${BASE}/executions/${id}/events${suffix}`
}

async function handle(res) {
  if (!res.ok) {
    let message = res.statusText
    try {
      const data = await res.json()
      if (data && data.detail) {
        message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
      }
    } catch (_) {
      /* ignore parse errors */
    }
    throw new Error(message)
  }
  return res.json()
}

export async function createExecution(userRequest) {
  const res = await fetch(`${BASE}/executions`, {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ user_request: userRequest }),
  })
  return handle(res)
}

export async function getExecution(id) {
  const res = await fetch(`${BASE}/executions/${id}`, { headers: headers() })
  return handle(res)
}

export async function listExecutions() {
  const res = await fetch(`${BASE}/executions`, { headers: headers() })
  return handle(res)
}

export async function getMetrics() {
  const res = await fetch(`${BASE}/metrics`, { headers: headers() })
  return handle(res)
}
