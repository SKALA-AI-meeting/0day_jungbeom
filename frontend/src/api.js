// The browser talks only to Spring Boot (/api/**). AI work is a task: 202 + taskId, progress over SSE.
const store = {
  get: (k) => { try { return localStorage.getItem(k) } catch { return null } },
  set: (k, v) => { try { localStorage.setItem(k, v) } catch { /* private mode: keep in memory only */ } },
  del: (k) => { try { localStorage.removeItem(k) } catch { /* ignore */ } },
}

export const auth = {
  admin: () => store.get('dz_admin_jwt'),
  setAdmin: (t) => store.set('dz_admin_jwt', t),
  clearAdmin: () => store.del('dz_admin_jwt'),
  candidate: (sid) => store.get(`dz_cand_${sid}`),
  setCandidate: (sid, t) => store.set(`dz_cand_${sid}`, t),
}

async function req(method, url, body, token) {
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = new Error((await res.json().catch(() => ({}))).detail || `요청 실패 (${res.status})`)
    err.status = res.status
    throw err
  }
  return res.status === 204 ? null : res.json()
}

const cand = (sid) => auth.candidate(sid)
const admin = () => auth.admin()

export const api = {
  meta: () => req('GET', '/api/meta'),
  preview: (scenarioId) => req('GET', `/api/scenarios/${scenarioId}`),
  invite: (token) => req('GET', `/api/invites/${encodeURIComponent(token)}`),
  startSession: (token, alias, scenarioId) => req('POST', `/api/invites/${encodeURIComponent(token)}/sessions`, { alias, scenarioId }),

  getSession: (sid) => req('GET', `/api/sessions/${sid}`, null, cand(sid)),
  saveNotes: (sid, text) => req('PUT', `/api/sessions/${sid}/notes`, { text }, cand(sid)),
  finish: (sid) => req('POST', `/api/sessions/${sid}/finish`, null, cand(sid)),
  submitTurn: (sid, text, choiceId) => req('POST', '/api/ai/tasks', { type: 'TURN', sessionId: sid, text, choiceId }, cand(sid)),
  myTasks: (token) => req('GET', '/api/ai/tasks?mine=true', null, token),

  signup: (companyName, email, password) => req('POST', '/api/auth/signup', { companyName, email, password }),
  login: (email, password) => req('POST', '/api/auth/login', { email, password }),
  me: () => req('GET', '/api/auth/me', null, admin()),
  adminList: () => req('GET', '/api/admin/sessions', null, admin()),
  adminGet: (sid) => req('GET', `/api/admin/sessions/${sid}`, null, admin()),
  adminInvites: () => req('GET', '/api/admin/invites', null, admin()),
  adminInvite: (alias, email) => req('POST', '/api/admin/invites', { alias, email: email || null }, admin()),
  requestReport: (sid) => req('POST', '/api/ai/tasks', { type: 'REPORT', sessionId: sid }, admin()),
  approve: (taskId, approved, comment) => req('POST', `/api/ai/tasks/${taskId}/approval`, { approved, comment }, admin()),
}

/**
 * Subscribe to a task's progress events (TOKEN, TOOL_START, TOOL_END, APPROVAL_REQUIRED, DONE, FAILED).
 * Uses fetch so the bearer token stays in a header (EventSource cannot set headers).
 */
export async function streamTask(taskId, token, onEvent) {
  const res = await fetch(`/api/ai/tasks/${taskId}/stream`, { headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' } })
  if (!res.ok || !res.body) throw new Error(`진행 상황을 받지 못했어요 (${res.status})`)
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
