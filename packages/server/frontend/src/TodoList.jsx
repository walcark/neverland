import { useState } from 'react'

import TodoEditor from './TodoEditor.jsx'

// A single row with its direct actions: complete, edit, toggle in/out of
// today's plan, delete. While editing, the row is replaced by the editor.
function TodoRow({ todo, vocab, inToday, onComplete, onDelete, onEdit, onToggleToday }) {
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)

  const run = (fn) => async () => {
    if (busy) return
    setBusy(true)
    try {
      await fn(todo.id)
    } finally {
      setBusy(false)
    }
  }

  async function save(fields) {
    setBusy(true)
    try {
      await onEdit(todo.id, fields)
      setEditing(false)
    } finally {
      setBusy(false)
    }
  }

  if (editing) {
    return (
      <li className="todo editing">
        <TodoEditor
          todo={todo}
          vocab={vocab}
          busy={busy}
          onSave={save}
          onCancel={() => setEditing(false)}
        />
      </li>
    )
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
        className={`today-toggle${inToday ? ' in-today' : ''}`}
        type="button"
        title={inToday ? "Remove from today" : "Add to today"}
        aria-label={inToday ? `Remove ${todo.title} from today` : `Add ${todo.title} to today`}
        onClick={run(onToggleToday)}
        disabled={busy}
      >
        {inToday ? '★ Today' : '☆ Today'}
      </button>
      <button
        className="row-edit"
        type="button"
        title="Edit"
        aria-label={`Edit ${todo.title}`}
        onClick={() => setEditing(true)}
        disabled={busy}
      >
        ✎
      </button>
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

export default function TodoList({
  todos,
  vocab,
  todayIds,
  onComplete,
  onDelete,
  onEdit,
  onToggleToday,
}) {
  if (todos.length === 0) {
    return <p className="empty">Nothing here.</p>
  }
  return (
    <ul className="todo-list">
      {todos.map((todo) => (
        <TodoRow
          key={todo.id}
          todo={todo}
          vocab={vocab}
          inToday={todayIds.has(todo.id)}
          onComplete={onComplete}
          onDelete={onDelete}
          onEdit={onEdit}
          onToggleToday={onToggleToday}
        />
      ))}
    </ul>
  )
}
