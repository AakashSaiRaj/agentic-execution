import { useCallback, useEffect, useState } from 'react'
import { createExecution, getExecution, listExecutions } from './api'
import TaskForm from './components/TaskForm'
import ExecutionView from './components/ExecutionView'
import StatusBadge from './components/StatusBadge'

const TERMINAL = new Set(['COMPLETED', 'FAILED'])
const POLL_INTERVAL_MS = 1500

export default function App() {
  const [execution, setExecution] = useState(null)
  const [recent, setRecent] = useState([])
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const busy = submitting || (execution != null && !TERMINAL.has(execution.status))

  const refreshRecent = useCallback(async () => {
    try {
      setRecent(await listExecutions())
    } catch (_) {
      /* non-critical */
    }
  }, [])

  useEffect(() => {
    refreshRecent()
  }, [refreshRecent])

  // Poll the current execution until it reaches a terminal state. The effect
  // only re-subscribes when the execution id or status changes (not on every
  // poll), which keeps a single steady 1.5s interval.
  useEffect(() => {
    const id = execution?.id
    const status = execution?.status
    if (!id || TERMINAL.has(status)) return undefined

    const timer = setInterval(async () => {
      try {
        const updated = await getExecution(id)
        setExecution(updated)
        if (TERMINAL.has(updated.status)) refreshRecent()
      } catch (e) {
        setError(e.message)
      }
    }, POLL_INTERVAL_MS)

    return () => clearInterval(timer)
  }, [execution?.id, execution?.status, refreshRecent])

  const handleSubmit = async (userRequest) => {
    setError('')
    setSubmitting(true)
    try {
      const created = await createExecution(userRequest)
      setExecution(created)
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
      setExecution(await getExecution(id))
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>AI Agent Execution Platform</h1>
        <p className="subtitle">
          Decompose a task, plan subtasks, run agents, and aggregate a result.
        </p>
      </header>

      <main className="layout">
        <div className="col-main">
          <TaskForm onSubmit={handleSubmit} busy={busy} />
          {error && <div className="card error-banner">{error}</div>}
          <ExecutionView execution={execution} />
        </div>

        <aside className="col-side">
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
