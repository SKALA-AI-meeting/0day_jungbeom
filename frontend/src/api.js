const adminHeaders = () => {
  const t = localStorage.getItem('dz_admin_token')
  return t ? { 'x-admin-token': t } : {}
}

async function req(method, url, body, admin = false) {
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', ...(admin ? adminHeaders() : {}) },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = new Error((await res.json().catch(() => ({}))).detail || `요청 실패 (${res.status})`)
    err.status = res.status
    throw err
  }
  return res.json()
}

export const api = {
  meta: () => req('GET', '/api/meta'),
  createSession: (alias, scenario_id) => req('POST', '/api/sessions', { alias, scenario_id }),
  getSession: (id) => req('GET', `/api/sessions/${id}`),
  saveNotes: (id, text) => req('PUT', `/api/sessions/${id}/notes`, { text }),
  finish: (id) => req('POST', `/api/sessions/${id}/finish`),
  adminList: () => req('GET', '/api/admin/sessions', null, true),
  adminGet: (id) => req('GET', `/api/admin/sessions/${id}`, null, true),
  adminRegenerate: (id) => req('POST', `/api/admin/sessions/${id}/report`, null, true),
}

/** POST a candidate message and stream SSE events to onEvent. */
export async function sendMessage(id, text, onEvent) {
  const res = await fetch(`/api/sessions/${id}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!res.ok || !res.body) throw new Error(`전송 실패 (${res.status})`)
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, i)
      buf = buf.slice(i + 2)
      if (chunk.startsWith('data: ')) onEvent(JSON.parse(chunk.slice(6)))
    }
  }
}
