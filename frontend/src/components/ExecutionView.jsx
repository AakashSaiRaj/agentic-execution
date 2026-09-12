import StatusBadge from './StatusBadge'

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

  return (
    <section className="card">
      <div className="exec-header">
        <h2>Execution</h2>
        <StatusBadge status={status} />
      </div>

      <p className="request">{user_request}</p>
      {isWorking && <p className="hint">Working… this updates automatically.</p>}

      <h3>Subtasks</h3>
      {tasks.length === 0 ? (
        <p className="muted">Planning subtasks…</p>
      ) : (
        <ol className="tasks">
          {tasks.map((task) => (
            <li key={task.id} className="task">
              <div className="task-top">
                <span className="agent">{task.agent_type}</span>
                <StatusBadge status={task.status} />
              </div>
              <p className="task-desc">{task.description}</p>
              {task.result && <pre className="output">{task.result.output}</pre>}
              {task.error && <pre className="output error-text">{task.error}</pre>}
            </li>
          ))}
        </ol>
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
