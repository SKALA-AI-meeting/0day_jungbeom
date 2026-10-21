// Who is signed in. One reactive store for the whole app; tokens persist per role in localStorage (best effort).
import { reactive } from 'vue'

// A module manifest's `role` is enough to add a role: router.js registers it, its token lives under dz_<role>_jwt.
const KEYS = { admin: 'dz_admin_jwt', candidate: 'dz_cand_jwt' }
const keyOf = (role) => KEYS[role] || `dz_${role}_jwt`
const read = (k) => { try { return localStorage.getItem(k) } catch { return null } }
const write = (k, v) => { try { v ? localStorage.setItem(k, v) : localStorage.removeItem(k) } catch { /* private mode */ } }

const state = reactive({
  admin: read(KEYS.admin),
  candidate: read(KEYS.candidate),
})

export const auth = {
  state,
  /** Make a manifest role known (idempotent); its token is read back from storage. */
  register(role) { if (role && !(role in state)) state[role] = read(keyOf(role)) },
  token: (role) => state[role] || null,
  set(role, t) { state[role] = t; write(keyOf(role), t) },
  clear(role) { state[role] = null; write(keyOf(role), null) },
  admin: () => state.admin,
  candidate: () => state.candidate,
  setAdmin(t) { auth.set('admin', t) },
  setCandidate(t) { auth.set('candidate', t) },
  clearAdmin() { auth.clear('admin') },
  clearCandidate() { auth.clear('candidate') },
  /** Called by the API client on 401 with the token that failed; main.js routes the user to that role's login. */
  expired(token) {
    const role = Object.keys(state).find((r) => token && state[r] === token)
    if (!role) return
    this.clear(role)
    this.onExpired?.(role)
  },
  onExpired: null,
}
