export default function ActivityLog({ events }) {
  if (!events || events.length === 0) return null
  // Most recent first.
  const ordered = [...events].reverse()
  return (
    <section className="card">
      <h3>Activity</h3>
      <ul className="activity">
        {ordered.map((e, i) => (
          <li key={`${e.t}-${i}`} className={`activity-item act-${e.kind}`}>
            <span className="activity-time">{e.t}</span>
            <span className="activity-dot" />
            <span className="activity-text">{e.text}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
