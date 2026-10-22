// Charts arrive as SVG strings from analytics-mcp (render_chart, api-contract §5). They are shown only as <img> data URIs:
// an image never runs scripts or fetches what its markup references, and the markup is never inserted into the page as HTML.
export const svgSrc = (svg) => 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)

/** Epoch seconds (or ms / ISO) -> "10. 22. 오후 03:04" */
export function fmtAt(t) {
  if (t == null) return ''
  const ms = typeof t === 'number' ? (t < 1e12 ? t * 1000 : t) : Date.parse(t)
  return Number.isFinite(ms) ? new Date(ms).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''
}
