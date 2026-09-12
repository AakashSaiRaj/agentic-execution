export function fmtDuration(ms) {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

export function fmtCost(cost) {
  if (cost == null) return '—'
  if (cost === 0) return '$0'
  return `$${cost.toFixed(4)}`
}

function Stat({ label, value }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}

export default function ExecutionStats({ execution }) {
  const { duration_ms, total_tokens, cost_usd, tasks = [] } = execution
  const toolCalls = tasks.reduce((n, t) => n + (t.tool_calls || 0), 0)
  return (
    <div className="stats">
      <Stat label="Duration" value={fmtDuration(duration_ms)} />
      <Stat label="Tasks" value={tasks.length} />
      <Stat label="Tokens" value={total_tokens ?? '—'} />
      <Stat label="Est. cost" value={fmtCost(cost_usd)} />
      <Stat label="Tool calls" value={toolCalls} />
    </div>
  )
}
