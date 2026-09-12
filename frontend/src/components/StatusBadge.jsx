const CLASS_BY_STATUS = {
  PENDING: 'badge-pending',
  PLANNING: 'badge-planning',
  RUNNING: 'badge-running',
  COMPLETED: 'badge-completed',
  FAILED: 'badge-failed',
}

export default function StatusBadge({ status }) {
  const cls = CLASS_BY_STATUS[status] || 'badge-pending'
  return <span className={`badge ${cls}`}>{status}</span>
}
