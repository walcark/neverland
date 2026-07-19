import { useCallback, useEffect, useState } from 'react'

import { completeTodo, deleteTodo, getTodos, getViews, getVocabulary } from './api.js'
import Clarify from './Clarify.jsx'
import QuickAdd from './QuickAdd.jsx'
import Sidebar from './Sidebar.jsx'
import TodoList from './TodoList.jsx'

const DEFAULT_SELECTION = { kind: 'view', value: 'inbox', label: 'Inbox' }

// Turn a sidebar selection into the /api/todos query it stands for.
function todosQuery(selection) {
  if (selection.kind === 'area') return ['all', { area: selection.value }]
  if (selection.kind === 'context') return ['all', { context: selection.value }]
  return [selection.value, {}]
}

export default function App() {
  const [views, setViews] = useState(null)
  const [vocab, setVocab] = useState({ areas: [], contexts: [] })
  const [selection, setSelection] = useState(DEFAULT_SELECTION)
  const [todos, setTodos] = useState([])
  const [clarifying, setClarifying] = useState(false)
  const [error, setError] = useState(null)

  const loadSidebar = useCallback(async () => {
    const [v, vocabulary] = await Promise.all([getViews(), getVocabulary()])
    setViews(v)
    setVocab(vocabulary)
  }, [])

  const loadTodos = useCallback(async () => {
    const [view, filters] = todosQuery(selection)
    setTodos(await getTodos(view, filters))
  }, [selection])

  useEffect(() => {
    loadSidebar().catch((e) => setError(String(e)))
  }, [loadSidebar])

  useEffect(() => {
    loadTodos().catch((e) => setError(String(e)))
  }, [loadTodos])

  // After any mutation, refresh both the list and the sidebar counts.
  const refresh = useCallback(() => {
    Promise.all([loadSidebar(), loadTodos()]).catch((e) => setError(String(e)))
  }, [loadSidebar, loadTodos])

  // Leaving a view stops any clarify session, so the button never lingers.
  const select = useCallback((next) => {
    setClarifying(false)
    setSelection(next)
  }, [])

  const onComplete = useCallback(
    async (id) => {
      await completeTodo(id)
      refresh()
    },
    [refresh],
  )

  const onDelete = useCallback(
    async (id) => {
      await deleteTodo(id)
      refresh()
    },
    [refresh],
  )

  const exitClarify = useCallback(() => {
    setClarifying(false)
    refresh()
  }, [refresh])

  const inInbox = selection.kind === 'view' && selection.value === 'inbox'
  const canClarify = inInbox && todos.length > 0 && !clarifying

  return (
    <div className="app">
      <Sidebar
        views={views}
        vocab={vocab}
        selection={selection}
        onSelect={select}
      />
      <main className="main">
        <header className="main-header">
          <h1>{selection.label}</h1>
          <span className="count">{todos.length}</span>
          {canClarify && (
            <button
              type="button"
              className="clarify-start"
              onClick={() => setClarifying(true)}
            >
              Clarify
            </button>
          )}
        </header>
        {error && <p className="error">{error}</p>}
        {clarifying ? (
          <Clarify items={todos} vocab={vocab} onExit={exitClarify} />
        ) : (
          <>
            <QuickAdd onCaptured={refresh} />
            <TodoList todos={todos} onComplete={onComplete} onDelete={onDelete} />
          </>
        )}
      </main>
    </div>
  )
}
