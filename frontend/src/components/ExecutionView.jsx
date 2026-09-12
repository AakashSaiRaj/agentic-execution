import StatusBadge from './StatusBadge'
import ExecutionStats, { fmtCost, fmtDuration } from './ExecutionStats'
import Timeline from './Timeline'

const TERMINAL = new Set(['COMPLETED', 'FAILED'])

export default function ExecutionView({ execution }) {
  if (!execution) {
    return (
      <section className="card muted-card">
        <p className="muted">Submit a task to see planning and execution here.</p>
      </section>
    )
  }

  const { user_request, status, tasks = [], final_result, error } = execution
  const isWorking = !TERMINAL.has(status)
  const completedCount = tasks.filter((t) => t.status === 'COMPLETED').length
  const progressPct = tasks.length ? Math.round((completedCount / tasks.length) * 100) : 0

  return (
    <section className="card">
      <div className="exec-header">
        <h2>Execution</h2>
        <StatusBadge status={status} />
      </div>

      <p className="request">{user_request}</p>
      {isWorking && <p className="hint">Working… this updates automatically.</p>}

      <ExecutionStats execution={execution} />
      {tasks.length > 0 && execution.started_at && (
        <>
          <h3>Timeline</h3>
          <Timeline execution={execution} />
        </>
      )}

      {tasks.length === 0 ? (
        <>
          <h3>Subtasks</h3>
          <p className="muted">Planning subtasks…</p>
        </>
      ) : (
        <>
          <div className="progress-row">
            <h3>Subtasks</h3>
            <span className="progress-label">
              {completedCount}/{tasks.length} completed
            </span>
          </div>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${progressPct}%` }} />
          </div>

          <ol className="tasks">
            {tasks.map((task) => (
              <li key={task.id} className="task">
                <div className="task-top">
                  <span className="agent">
                    <span className="task-index">#{task.order_index}</span> {task.agent_type}
                    {task.attempts > 0 && (
                      <span className="attempts" title="retry attempts">
                        · attempt {task.attempts + 1}
                      </span>
                    )}
                  </span>
                  <StatusBadge status={task.status} />
                </div>
                <p className="task-desc">{task.description}</p>
                {task.depends_on && task.depends_on.length > 0 ? (
                  <div className="deps">
                    depends on {task.depends_on.map((d) => `#${d}`).join(', ')}
                  </div>
                ) : (
                  <div className="deps independent">independent (runs immediately)</div>
                )}
                {(task.status === 'COMPLETED' || task.tool_calls > 0) && (
                  <div className="task-meta">
                    {task.duration_ms != null && <span>{fmtDuration(task.duration_ms)}</span>}
                    {task.total_tokens != null && <span>{task.total_tokens} tokens</span>}
                    {task.cost_usd != null && <span>{fmtCost(task.cost_usd)}</span>}
                    {task.tool_calls > 0 && <span>{task.tool_calls} tool call{task.tool_calls > 1 ? 's' : ''}</span>}
                  </div>
                )}
                {task.result && <pre className="output">{task.result.output}</pre>}
                {task.error && <pre className="output error-text">{task.error}</pre>}
              </li>
            ))}
          </ol>
        </>
      )}

      {status === 'COMPLETED' && final_result && (
        <div className="final">
          <h3>Final result</h3>
          <pre className="output final-output">{final_result}</pre>
        </div>
      )}
      {status === 'FAILED' && error && (
        <div className="final">
          <h3>Error</h3>
          <pre className="output error-text">{error}</pre>
        </div>
      )}
    </section>
  )
}
