# web

Next.js App Router + Tailwind v4. 설계: `docs/frontend/design.md`. 계약: `docs/common/contracts.md`.

```
pnpm install
pnpm dev                      # http://localhost:3000, api는 NEXT_PUBLIC_API_URL
NEXT_PUBLIC_MOCK=1 pnpm dev   # mocks/의 계약 예시로 동작
pnpm test && pnpm lint
```

- 토큰: `app/globals.css`의 `@theme`(색·타이포·간격·모서리)
- 공용 컴포넌트: `components/ui/`(base-ui 프리미티브 + cva). props는 고정, 내부 모양은 web-polish가 다듬는다
- 라이브러리 선택은 `emilkowalski/skills`의 pick-ui-library 기준: 프리미티브 base-ui, 클래스 clsx, 변형 cva
