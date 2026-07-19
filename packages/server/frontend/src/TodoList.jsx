import { useState } from 'react'

// A single row, with its two direct actions: complete (archive) and delete.
// Both disable the row while in flight so a double click cannot fire twice.
function TodoRow({ todo, onComplete, onDelete }) {
  const [busy, setBusy] = useState(false)

  const run = (fn) => async () => {
    if (busy) return
    setBusy(true)
    try {
      await fn(todo.id)
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className={`todo${busy ? ' busy' : ''}`}>
      <button
        className="check"
        type="button"
        title="Complete"
        aria-label={`Complete ${todo.title}`}
        onClick={run(onComplete)}
        disabled={busy}
      >
        ✓
      </button>
      <span className={`pill state-${todo.state}`}>{todo.state}</span>
      <span className="todo-title">{todo.title}</span>
      <span className="todo-tags">
        {todo.context && <span className="tag context">{todo.context}</span>}
        {todo.area && <span className="tag area">{todo.area}</span>}
        {todo.waiting_on && <span className="tag waiting">{todo.waiting_on}</span>}
      </span>
      <button
        className="row-del"
        type="button"
        title="Delete"
        aria-label={`Delete ${todo.title}`}
        onClick={run(onDelete)}
        disabled={busy}
      >
        ✕
      </button>
    </li>
  )
}

export default function TodoList({ todos, onComplete, onDelete }) {
  if (todos.length === 0) {
    return <p className="empty">Nothing here.</p>
  }
  return (
    <ul className="todo-list">
      {todos.map((todo) => (
        <TodoRow
          key={todo.id}
          todo={todo}
          onComplete={onComplete}
          onDelete={onDelete}
        />
      ))}
    </ul>
  )
}
