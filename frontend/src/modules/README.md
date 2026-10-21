# Frontend modules

Each folder is one product area. `index.js` exports a module manifest and the shell composes everything from it:

```js
export default {
  id: 'candidate',          // route.meta.module
  role: 'candidate',        // routes need this sign-in unless the route sets meta.public
  login: '/login',          // where the guard sends a signed-out visitor
  home: '/me',              // landing page of the area after sign-in
  nav: [{ to: '/me', label: '내 평가' }],   // top bar links, shown while inside the area
  routes: [{ path: '/me', component: () => import('./Me.vue'), meta: { title: '내 평가' } }],
}
```

Adding a page = add a route (and optionally a nav item) to a manifest. Adding an area = add a folder and list it in `modules/index.js`.
