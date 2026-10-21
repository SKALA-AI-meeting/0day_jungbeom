// The admin's issue checklist (what the agent is waiting on a person for). Shared by the top-bar badge and the pages.
import { reactive } from 'vue'
import { api } from '../api'

export const inbox = reactive({ items: [], count: 0, loaded: false })

export async function refreshInbox() {
  const r = await api.inbox()
  inbox.items = r.items
  inbox.count = r.count
  inbox.loaded = true
  return r
}
