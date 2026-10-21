// The browser talks only to Spring Boot (/api/**). AI work is a task: 202 + taskId, progress over SSE.
import { auth } from './state/auth'

export { auth }

async function req(method, url, body, token) {
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    if (res.status === 401 && token) auth.expired(token) // a stale token: sign that role out and send it to its login
    const err = new Error((await res.json().catch(() => ({}))).detail || `요청 실패 (${res.status})`)
    err.status = res.status
    throw err
  }
  return res.status === 204 ? null : res.json()
}

const cand = () => auth.candidate()
const admin = () => auth.admin()

export const api = {
  // public
  meta: () => req('GET', '/api/meta'),
  preview: (scenarioId) => req('GET', `/api/scenarios/${scenarioId}`),
  invite: (token) => req('GET', `/api/invites/${encodeURIComponent(token)}`),

  // candidate account
  candidateSignup: (data) => req('POST', '/api/auth/candidate/signup', data),
  candidateLogin: (email, password) => req('POST', '/api/auth/candidate/login', { email, password }),
  me: () => req('GET', '/api/me', null, cand()),
  mySessions: () => req('GET', '/api/me/sessions', null, cand()),
  startSession: (scenarioId, inviteToken) => req('POST', '/api/me/sessions', { scenarioId, inviteToken: inviteToken || null }, cand()),

  // candidate session
  getSession: (sid) => req('GET', `/api/sessions/${sid}`, null, cand()),
  saveNotes: (sid, text) => req('PUT', `/api/sessions/${sid}/notes`, { text }, cand()),
  finish: (sid) => req('POST', `/api/sessions/${sid}/finish`, null, cand()),
  submitTurn: (sid, text, choiceId) => req('POST', '/api/ai/tasks', { type: 'TURN', sessionId: sid, text, choiceId }, cand()),
  myTasks: (token) => req('GET', '/api/ai/tasks?mine=true', null, token),

  // admin
  signup: (companyName, email, password) => req('POST', '/api/auth/signup', { companyName, email, password }),
  login: (email, password) => req('POST', '/api/auth/login', { email, password }),
  adminMe: () => req('GET', '/api/auth/me', null, admin()),
  inbox: () => req('GET', '/api/admin/inbox', null, admin()),
  accounts: () => req('GET', '/api/admin/accounts', null, admin()),
  decideAccount: (id, approved, comment) => req('POST', `/api/admin/accounts/${id}/decision`, { approved, comment }, admin()),
  adminList: () => req('GET', '/api/admin/sessions', null, admin()),
  adminGet: (sid) => req('GET', `/api/admin/sessions/${sid}`, null, admin()),
  adminInvites: () => req('GET', '/api/admin/invites', null, admin()),
  adminInvite: (alias, email) => req('POST', '/api/admin/invites', { alias, email: email || null }, admin()),
  requestReport: (sid) => req('POST', '/api/ai/tasks', { type: 'REPORT', sessionId: sid }, admin()),
  approve: (taskId, approved, comment) => req('POST', `/api/ai/tasks/${taskId}/approval`, { approved, comment }, admin()),
  task: (taskId, token) => req('GET', `/api/ai/tasks/${taskId}`, null, token),
}

/** Read a text/event-stream with fetch so the bearer token stays in a header (EventSource cannot set headers). */
export async function streamSSE(url, token, onEvent) {
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' } })
  if (!res.ok || !res.body) {
    if (res.status === 401) auth.expired(token)
    const err = new Error(`진행 상황을 받지 못했어요 (${res.status})`)
    err.status = res.status
    throw err
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    let i
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, i)
      buf = buf.slice(i + 2)
      let type = 'message'
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) type = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).replace(/^ /, '')
      }
      if (data) onEvent({ type, data: JSON.parse(data) })
    }
  }
}

/** Progress events of one task (TOKEN, TOOL_START, TOOL_END, PROGRESS, APPROVAL_REQUIRED, DONE, FAILED). */
export const streamTask = (taskId, token, onEvent) => streamSSE(`/api/ai/tasks/${taskId}/stream`, token, onEvent)
/** The signed-in candidate's account review, stage names only. */
export const streamReview = (onEvent) => streamSSE('/api/me/review/stream', auth.candidate(), onEvent)
