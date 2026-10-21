// Module registry: the router and the top bar are built from these manifests (see README.md).
import publicArea from './public'
import candidate from './candidate'
import admin from './admin'

export const modules = [publicArea, candidate, admin]
export const moduleById = Object.fromEntries(modules.map((m) => [m.id, m]))
