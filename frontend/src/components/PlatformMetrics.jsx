export default function PlatformMetrics({ metrics }) {
  if (!metrics) return null
  const ex = metrics.executions || {}
  const tk = metrics.tasks || {}
  const llm = metrics.llm || {}
  const tools = metrics.tools || {}
  const dur = metrics.durations_ms || {}
  const q = metrics.queue || {}

  const rows = [
    ['Executions', ex.total ?? 0],
    ['Tasks', tk.total ?? 0],
    ['Avg task', dur.task_avg != null ? `${Math.round(dur.task_avg)} ms` : '—'],
    ['Tokens', llm.total_tokens ?? 0],
    ['Est. cost', `$${(llm.total_cost_usd ?? 0).toFixed(4)}`],
    ['Tool calls', tools.total_calls ?? 0],
  ]
  if (q.dead_letter_depth != null) rows.push(['Dead-letter', q.dead_letter_depth])

  return (
    <div className="card">
      <h3>Platform metrics</h3>
      <ul className="metrics-list">
        {rows.map(([label, value]) => (
          <li key={label}>
            <span>{label}</span>
            <b>{value}</b>
          </li>
        ))}
      </ul>
    </div>
  )
}
