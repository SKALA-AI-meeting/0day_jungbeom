# Frontend modules

Each folder is one product area. `index.js` exports a module manifest and the shell composes everything from it:

```js
export default {
  id: 'candidate',          // route.meta.module
  role: 'candidate',        // routes need this sign-in unless the route sets meta.public
  login: '/login',          // where the guard sends a signed-out visitor
  home: '/me',              // landing page of the area after sign-in
  signOutTo: '/',           // optional: where 로그아웃 goes (default '/')
  brand: '…',               // optional: label next to the logo (default '협업 대화 관찰')
  who: async () => '닉네임', // optional: name shown in the top bar while signed in
  nav: [{ to: '/me', label: '내 평가' }],   // top bar links, shown while inside the area
  routes: [{ path: '/me', component: () => import('./Me.vue'), meta: { title: '내 평가' } }],
}
```

Adding a page = add a route (and optionally a nav item) to a manifest. Adding an area = add a folder and list it in `modules/index.js`;
that also works for a new `role`: `router.js` registers every manifest role with `state/auth.js` (`auth.token(role)`, `auth.set(role, t)`,
`auth.clear(role)`, token stored as `dz_<role>_jwt`), and the guard and top bar read only the manifest. The sign-in page of a new role calls
`auth.set('<role>', token)`; Spring still decides what the token may do.
The manifests stay the only place pages are registered; overlays such as the artifact drawer are components, not routes.

## Shared pieces outside the modules

- `src/api.js` — every browser call to Spring (`/api/**`). Add new endpoints here, named after what they do (`addAnnotation`, `restartSession`, `dismissReport`).
  `streamTask(taskId, token, onEvent, signal?)` follows a task's SSE; pass an `AbortSignal` to stop listening early (it rejects with `AbortError`).
- `src/utils/markdown.js` — `renderMarkdown(text, { lines? })` is the only way stored text becomes HTML (markdown-it with raw HTML off, KaTeX for
  `$…$ $$…$$ \(…\) \[…\]`, DOMPurify last). Never `v-html` anything that did not come out of it. Wrap the result in an element with class `md`
  (global styles in `style.css`). `lines: true` tags blocks with `data-ls`/`data-le` (1-based source lines) for line-anchored UIs.
- `src/utils/artifacts.js` — labels for artifact kinds and markup kinds, and `normArtifacts` / `normAnnotation` / `normCheck`, which accept both
  the browser (camelCase) and agent (snake_case) shapes from `docs/architecture/api-contract.md`. Read artifacts through these.
- `src/components/` — `ArtifactTable` + `ArtifactViewer` (shared by the candidate session and the admin detail; the viewer takes async `save` / `remove`
  functions so the page owns the API calls), `MilestoneStepper`, `StageChecklist`, `CheckMark` (`delay` staggers several checks), `ChatBubble`.

## Admin issue checklist (`admin/Inbox.vue` → `admin/Working.vue`)

An inbox item kind needs a row in `KIND` (chip) and, when deciding it is not a task approval, an entry in `DECIDE` that returns
`{ taskId, fresh }` (a task to follow) or `{ manual: true }`. Button labels come from `item.actions` with the per-kind fallbacks in `ACTIONS`.
`Working.vue` counts a followed task as settled when it is DONE / REJECTED / FAILED, or when it stops for a person again (`WAITING_APPROVAL`);
in the last case it forwards to the checklist instead of the dashboard.

## Motion

Animations respect `prefers-reduced-motion` (each component turns its own off). Colours come from the tokens on `:root` so dark mode keeps working;
fixed hues are mixed with `color-mix(..., transparent)` rather than hard light backgrounds.
