// Markdown + LaTeX for persona lines, candidate messages and shared artifacts (api-contract §4).
// Text is stored raw; this is the only place it becomes HTML: markdown-it (raw HTML off) -> KaTeX -> DOMPurify.
import MarkdownIt from 'markdown-it'
import katex from 'katex'
import DOMPurify from 'dompurify'
import 'katex/dist/katex.min.css'

const texCache = new Map() // a streaming bubble re-renders the same formulas on every token

function tex(src, display) {
  const key = (display ? 'D' : 'I') + src
  let html = texCache.get(key)
  if (html == null) {
    try {
      html = katex.renderToString(src, { displayMode: display, throwOnError: false, strict: 'ignore', trust: false, maxSize: 20, maxExpand: 300 })
    } catch {
      html = `<code class="tex-err">${md.utils.escapeHtml(src)}</code>`
    }
    if (texCache.size > 400) texCache.delete(texCache.keys().next().value)
    texCache.set(key, html)
  }
  return html
}

const isSpace = (c) => c === undefined || /\s/.test(c)

/** Inline math: $…$, $$…$$, \(…\), \[…\]. A lone `$` (prices, "$5와 $10") stays text: pandoc's open/close rules. */
function mathInline(state, silent) {
  const { src, pos, posMax } = state
  let open, close, display
  if (src.startsWith('$$', pos)) [open, close, display] = ['$$', '$$', true]
  else if (src[pos] === '$') [open, close, display] = ['$', '$', false]
  else if (src.startsWith('\\(', pos)) [open, close, display] = ['\\(', '\\)', false]
  else if (src.startsWith('\\[', pos)) [open, close, display] = ['\\[', '\\]', true]
  else return false

  const from = pos + open.length
  let end = src.indexOf(close, from)
  if (open === '$') {
    if (isSpace(src[from])) return false
    while (end !== -1 && (isSpace(src[end - 1]) || src[end - 1] === '\\' || /\d/.test(src[end + 1] || ''))) end = src.indexOf('$', end + 1)
  }
  if (end === -1 || end + close.length > posMax || !src.slice(from, end).trim()) return false
  if (!silent) {
    const t = state.push(display ? 'math_display' : 'math_inline', 'math', 0)
    t.content = src.slice(from, end)
    t.markup = open
  }
  state.pos = end + close.length
  return true
}

/** Block math: a line starting with $$ or \[ up to the line that ends with $$ or \]. Unclosed (still streaming) stays text. */
function mathBlock(state, startLine, endLine, silent) {
  if (state.sCount[startLine] - state.blkIndent >= 4) return false
  const lineAt = (n) => state.src.slice(state.bMarks[n] + state.tShift[n], state.eMarks[n])
  const first = lineAt(startLine)
  const [open, close] = first.startsWith('$$') ? ['$$', '$$'] : first.startsWith('\\[') ? ['\\[', '\\]'] : []
  if (!open) return false

  const rest = first.slice(open.length).trimEnd()
  const parts = []
  let last = startLine
  let found = false
  if (rest.length >= close.length && rest.endsWith(close)) {
    parts.push(rest.slice(0, -close.length))
    found = true
  } else {
    parts.push(rest)
    for (let n = startLine + 1; n < endLine; n++) {
      const l = lineAt(n).trimEnd()
      if (state.sCount[n] < state.blkIndent && l) break
      last = n
      if (l.endsWith(close)) { parts.push(l.slice(0, -close.length)); found = true; break }
      parts.push(l)
    }
  }
  const content = parts.join('\n')
  if (!found || !content.trim()) return false
  if (silent) return true
  const t = state.push('math_block', 'math', 0)
  t.block = true
  t.content = content
  t.markup = open
  t.map = [startLine, last + 1]
  state.line = last + 1
  return true
}

// Blocks that carry their source line range when rendering an artifact (data-ls / data-le, 1-based, inclusive).
const LINE_BLOCKS = new Set(['paragraph_open', 'heading_open', 'list_item_open', 'tr_open', 'fence', 'code_block', 'hr', 'math_block'])

const md = new MarkdownIt({ html: false, linkify: true, breaks: true, typographer: false })
md.inline.ruler.before('escape', 'math_inline', mathInline)
md.block.ruler.before('fence', 'math_block', mathBlock, { alt: ['paragraph', 'reference', 'blockquote', 'list'] })
md.core.ruler.push('line_attrs', (state) => {
  if (!state.env?.lines) return
  for (const t of state.tokens) {
    if (t.map && LINE_BLOCKS.has(t.type)) {
      t.attrSet('data-ls', String(t.map[0] + 1))
      t.attrSet('data-le', String(Math.max(t.map[0] + 1, t.map[1])))
    }
  }
})
md.renderer.rules.math_inline = (tokens, i) => tex(tokens[i].content, false)
md.renderer.rules.math_display = (tokens, i) => `<span class="math-display">${tex(tokens[i].content, true)}</span>`
md.renderer.rules.math_block = (tokens, i, _o, _e, self) => `<div class="math-block"${self.renderAttrs(tokens[i])}>${tex(tokens[i].content, true)}</div>\n`
md.renderer.rules.table_open = (tokens, i, o, _e, self) => `<div class="md-table">${self.renderToken(tokens, i, o)}`
md.renderer.rules.table_close = (tokens, i, o, _e, self) => `${self.renderToken(tokens, i, o)}</div>`

DOMPurify.addHook?.('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A' && node.getAttribute('href')) {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer nofollow')
  }
})
const PURIFY = { ADD_ATTR: ['target'], ADD_FORBID_CONTENTS: ['annotation'] } // KaTeX's TeX annotation is not allowed MathML; drop it whole

/**
 * Markdown (+ $…$ math) -> sanitized HTML for v-html.
 * `lines: true` tags block elements with their source line range so an artifact viewer can select and highlight lines.
 */
export function renderMarkdown(src, { lines = false } = {}) {
  const text = String(src ?? '')
  if (!text) return ''
  const html = md.render(text, { lines })
  if (!DOMPurify.isSupported) return `<p>${md.utils.escapeHtml(text)}</p>` // no DOM (never true in a browser): never trust raw output
  return DOMPurify.sanitize(html, PURIFY)
}

/** Plain text of a markdown line, for short previews (chips, tooltips). */
export const stripMarkdown = (s) => String(s ?? '').replace(/[*_`#>~]|\[(.*?)\]\(.*?\)/g, '$1').replace(/\s+/g, ' ').trim()
