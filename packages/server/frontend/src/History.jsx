import { useEffect, useState } from 'react'

import { getDone } from './api.js'

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString()
}

// The archive: completed todos, most recently completed first. Read-only, so
// the log stays a faithful record of what was done and when.
export default function History() {
  const [todos, setTodos] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    getDone()
      .then(setTodos)
      .catch((e) => setError(String(e)))
  }, [])

  if (error) return <p className="error">{error}</p>
  if (todos.length === 0) return <p className="empty">No history yet.</p>

  return (
    <ul className="todo-list">
      {todos.map((todo) => (
        <li key={todo.id} className="todo done">
          <span className="pill state-done">done</span>
          <span className="todo-title">{todo.title}</span>
          <span className="todo-tags">
            {todo.context && <span className="tag context">{todo.context}</span>}
            {todo.area && <span className="tag area">{todo.area}</span>}
            {todo.completed && <span className="tag date">{formatDate(todo.completed)}</span>}
          </span>
        </li>
      ))}
    </ul>
  )
}
