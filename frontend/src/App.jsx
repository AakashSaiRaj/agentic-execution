import { useCallback, useEffect, useRef, useState } from 'react'
import { createExecution, getExecution, getMetrics, listExecutions } from './api'
import TaskForm from './components/TaskForm'
import ExecutionView from './components/ExecutionView'
import ActivityLog from './components/ActivityLog'
import PlatformMetrics from './components/PlatformMetrics'
import StatusBadge from './components/StatusBadge'

const TERMINAL = new Set(['COMPLETED', 'FAILED'])

// Derive human-readable activity events by diffing two execution snapshots.
function diffEvents(prev, next) {
  const events = []
  const stamp = () => new Date().toLocaleTimeString()
  const prevTasks = new Map((prev?.tasks || []).map((t) => [t.id, t]))

  for (const task of next.tasks || []) {
    const before = prevTasks.get(task.id)
    if (before && before.status === task.status) continue
    const label = {
      RUNNING: 'started',
      RETRYING: `retrying (attempt ${task.attempts})`,
      COMPLETED: 'completed',
      FAILED: 'failed',
    }[task.status]
    if (!label) continue // skip PENDING noise
    events.push({
      t: stamp(),
      kind: task.status.toLowerCase(),
      text: `#${task.order_index} ${task.agent_type} → ${label}`,
    })
  }

  if (prev && prev.status !== next.status) {
    if (next.status === 'COMPLETED') {
      events.push({ t: stamp(), kind: 'completed', text: 'Final result aggregated' })
    } else if (next.status === 'FAILED') {
      events.push({ t: stamp(), kind: 'failed', text: 'Execution failed' })
    } else if (next.status === 'RUNNING') {
      events.push({ t: stamp(), kind: 'running', text: 'Execution running' })
    }
  }
  return events
}

export default function App() {
  const [execution, setExecution] = useState(null)
  const [events, setEvents] = useState([])
  const [recent, setRecent] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const prevSnapshotRef = useRef(null)
  const esRef = useRef(null)

  const busy = submitting || (execution != null && !TERMINAL.has(execution.status))

  const refreshRecent = useCallback(async () => {
    try {
      setRecent(await listExecutions())
    } catch (_) {
      /* non-critical */
    }
  }, [])

  const refreshMetrics = useCallback(async () => {
    try {
      setMetrics(await getMetrics())
    } catch (_) {
      /* non-critical */
    }
  }, [])

  useEffect(() => {
    refreshRecent()
    refreshMetrics()
    const timer = setInterval(refreshMetrics, 4000)
    return () => clearInterval(timer)
  }, [refreshRecent, refreshMetrics])

  const applySnapshot = useCallback((next) => {
    setEvents((prevEvents) => {
      const additions = diffEvents(prevSnapshotRef.current, next)
      return additions.length ? [...prevEvents, ...additions].slice(-100) : prevEvents
    })
    prevSnapshotRef.current = next
    setExecution(next)
  }, [])

  // Real-time updates via Server-Sent Events (no client polling).
  useEffect(() => {
    const id = execution?.id
    const status = execution?.status
    if (!id || TERMINAL.has(status)) return undefined

    const es = new EventSource(`/api/executions/${id}/events`)
    esRef.current = es

    es.addEventListener('update', (e) => {
      try {
        applySnapshot(JSON.parse(e.data))
      } catch (_) {
        /* ignore malformed frame */
      }
    })
    es.addEventListener('done', () => {
      es.close()
      refreshRecent()
      refreshMetrics()
    })
    es.onerror = () => {
      // Connection dropped; close and take a one-shot REST snapshot.
      es.close()
      getExecution(id).then(applySnapshot).catch(() => {})
    }

    return () => es.close()
  }, [execution?.id, execution?.status, applySnapshot, refreshRecent, refreshMetrics])

  const startExecution = (snapshot) => {
    prevSnapshotRef.current = null
    setEvents([])
    applySnapshot(snapshot)
  }

  const handleSubmit = async (userRequest) => {
    setError('')
    setSubmitting(true)
    try {
      startExecution(await createExecution(userRequest))
      refreshRecent()
    } catch (e) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const openExecution = async (id) => {
    setError('')
    try {
      startExecution(await getExecution(id))
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>AI Agent Execution Platform</h1>
        <p className="subtitle">
          Decompose a task, plan subtasks, run agents concurrently, and aggregate a result.
        </p>
      </header>

      <main className="layout">
        <div className="col-main">
          <TaskForm onSubmit={handleSubmit} busy={busy} />
          {error && <div className="card error-banner">{error}</div>}
          <ExecutionView execution={execution} />
          <ActivityLog events={events} />
        </div>

        <aside className="col-side">
          <PlatformMetrics metrics={metrics} />
          <div className="card">
            <div className="side-header">
              <h3>Recent executions</h3>
              <button className="link" onClick={refreshRecent} type="button">
                refresh
              </button>
            </div>
            {recent.length === 0 ? (
              <p className="muted">No executions yet.</p>
            ) : (
              <ul className="recent">
                {recent.map((item) => (
                  <li key={item.id}>
                    <button
                      className="recent-item"
                      type="button"
                      onClick={() => openExecution(item.id)}
                    >
                      <span className="recent-req">{item.user_request}</span>
                      <StatusBadge status={item.status} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
      </main>
    </div>
  )
}
