// Shared work items ("같이 확인할 과제") and the candidate's markups on them (api-contract §1).
// The browser API is camelCase; the admin view may pass agent-side snake_case through, so everything is read via these.

export const KIND = {
  design: { label: '설계·기획', short: '기획안', tone: 'blue' },
  result: { label: '결과', short: '결과표', tone: 'green' },
  code: { label: '코드', short: '코드', tone: 'gray' },
}
export const MARK = {
  question: { label: '질문', color: '#2563eb' },
  risk: { label: '우려', color: '#d97706' },
  suggest: { label: '제안', color: '#7c3aed' },
  ok: { label: '확인함', color: '#16a34a' },
}
export const MARK_KINDS = Object.keys(MARK)
export const OWNER_TEAM = { name: '팀 공동', emoji: '👥' }

const toMs = (t) => (t == null ? null : typeof t === 'number' ? (t < 1e12 ? t * 1000 : t) : Date.parse(t))

export function normAnnotation(n) {
  const a = n.anchor || {}
  return {
    id: n.id,
    artifactId: n.artifactId ?? n.artifact_id,
    anchor: { lineStart: a.lineStart ?? a.line_start ?? null, lineEnd: a.lineEnd ?? a.line_end ?? null, quote: a.quote ?? null },
    kind: n.kind,
    text: n.text || '',
    msgIdx: n.msgIdx ?? n.msg_idx ?? null,
    createdAt: toMs(n.createdAt ?? n.created_at),
  }
}

/** Artifacts with their annotations attached; `loose` are annotations listed beside the artifacts (admin view). */
export function normArtifacts(list, loose = []) {
  const extra = (loose || []).map(normAnnotation)
  return (list || []).map((a) => {
    const own = (a.annotations || []).map(normAnnotation)
    const ids = new Set(own.map((n) => n.id))
    const more = extra.filter((n) => n.artifactId === a.id && !ids.has(n.id))
    return { ...a, lang: a.lang || null, body: a.body || '', annotations: [...own, ...more].sort((x, y) => x.id - y.id) }
  })
}

export function normCheck(c) {
  return {
    artifactId: c.artifactId ?? c.artifact_id,
    line: c.line,
    issue: c.issue || '',
    spotted: !!c.spotted,
    annotationIds: c.annotationIds ?? c.annotation_ids ?? [],
  }
}

export const lineCount = (body) => String(body ?? '').split('\n').length

/** 1-based [start, end] the annotation covers; a quote-only markup resolves to the lines its text sits on. */
export function annRange(n, body) {
  const { lineStart, lineEnd, quote } = n.anchor
  if (lineStart) return [lineStart, lineEnd || lineStart]
  if (!quote) return null
  const at = String(body ?? '').indexOf(quote)
  if (at < 0) return null
  const start = body.slice(0, at).split('\n').length
  return [start, start + quote.split('\n').length - 1]
}

export const rangeLabel = (s, e) => (!s ? '' : s === e || !e ? `L${s}` : `L${s}–${e}`)

export function anchorLabel(n) {
  const { lineStart, lineEnd, quote } = n.anchor
  if (lineStart) return rangeLabel(lineStart, lineEnd)
  return quote ? `“${quote.length > 18 ? quote.slice(0, 18) + '…' : quote}”` : ''
}

/** What "대화에 인용" puts into the chat draft, e.g. [재참여 개선 기획안 L12-14]. */
export function citeRef(artifact, s, e) {
  const t = artifact.title.length > 20 ? artifact.title.slice(0, 19) + '…' : artifact.title
  return `[${t}${s ? ` L${s}${e && e !== s ? `-${e}` : ''}` : ''}]`
}
