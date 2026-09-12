// Thin API client. All calls go through the Vite dev-server proxy at /api.

const BASE = '/api'

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
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_request: userRequest }),
  })
  return handle(res)
}

export async function getExecution(id) {
  const res = await fetch(`${BASE}/executions/${id}`)
  return handle(res)
}

export async function listExecutions() {
  const res = await fetch(`${BASE}/executions`)
  return handle(res)
}

export async function getMetrics() {
  const res = await fetch(`${BASE}/metrics`)
  return handle(res)
}
