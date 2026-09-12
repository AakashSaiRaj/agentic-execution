import { useState } from 'react'

const EXAMPLES = [
  'Research the impact of remote work on software team productivity.',
  'Compare REST and gRPC for a high-throughput internal microservice.',
  'Summarize the trade-offs of using Redis as a job queue.',
]

export default function TaskForm({ onSubmit, busy }) {
  const [value, setValue] = useState('')

  const submit = (event) => {
    event.preventDefault()
    const trimmed = value.trim()
    if (trimmed.length < 3) return
    onSubmit(trimmed)
  }

  return (
    <form onSubmit={submit} className="card">
      <h2>New task</h2>
      <textarea
        className="task-input"
        rows={4}
        placeholder="Describe a complex task to decompose and execute…"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={busy}
      />
      <div className="examples">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            className="chip"
            onClick={() => setValue(example)}
            disabled={busy}
          >
            {example}
          </button>
        ))}
      </div>
      <button type="submit" className="primary" disabled={busy || value.trim().length < 3}>
        {busy ? 'Running…' : 'Run task'}
      </button>
    </form>
  )
}
