function parse(ts) {
  return ts ? Date.parse(ts) : null
}

export default function Timeline({ execution }) {
  const start = parse(execution.started_at)
  if (!start) return null

  const end = parse(execution.completed_at) || Date.now()
  const total = Math.max(1, end - start)
  const tasks = [...(execution.tasks || [])].sort((a, b) => a.order_index - b.order_index)

  return (
    <div className="timeline">
      {tasks.map((t) => {
        const s = parse(t.started_at)
        return (
          <div key={t.id} className="tl-row">
            <span className="tl-label">
              #{t.order_index} {t.agent_type}
            </span>
            <div className="tl-track">
              {s == null ? (
                <div className="tl-waiting">waiting…</div>
              ) : (
                (() => {
                  const e = parse(t.completed_at) || Date.now()
                  const left = Math.max(0, ((s - start) / total) * 100)
                  const width = Math.max(2, Math.min(((e - s) / total) * 100, 100 - left))
                  const dur = t.duration_ms != null ? `${t.duration_ms} ms` : ''
                  return (
                    <div
                      className={`tl-bar tl-${t.status.toLowerCase()}`}
                      style={{ left: `${left}%`, width: `${width}%` }}
                      title={`${t.agent_type}: ${dur}`}
                    />
                  )
                })()
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
