// Who is signed in. One reactive store for the whole app; tokens persist per role in localStorage (best effort).
import { reactive } from 'vue'

const KEYS = { admin: 'dz_admin_jwt', candidate: 'dz_cand_jwt' }
const read = (k) => { try { return localStorage.getItem(k) } catch { return null } }
const write = (k, v) => { try { v ? localStorage.setItem(k, v) : localStorage.removeItem(k) } catch { /* private mode */ } }

const state = reactive({
  admin: read(KEYS.admin),
  candidate: read(KEYS.candidate),
})

export const auth = {
  state,
  admin: () => state.admin,
  candidate: () => state.candidate,
  setAdmin(t) { state.admin = t; write(KEYS.admin, t) },
  setCandidate(t) { state.candidate = t; write(KEYS.candidate, t) },
  clearAdmin() { state.admin = null; write(KEYS.admin, null) },
  clearCandidate() { state.candidate = null; write(KEYS.candidate, null) },
  /** Called by the API client on 401 with the token that failed; main.js routes the user to that role's login. */
  expired(token) {
    const role = token === state.admin ? 'admin' : token === state.candidate ? 'candidate' : null
    if (!role) return
    role === 'admin' ? this.clearAdmin() : this.clearCandidate()
    this.onExpired?.(role)
  },
  onExpired: null,
}
