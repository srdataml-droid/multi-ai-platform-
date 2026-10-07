# Account-free enquiry demo

The `/demo` route demonstrates website enquiry capture, owner review, editing a callback window, approval/decline and a simulated callback plan. The sign-in page links to it. It reuses the existing Next.js app and UI components; production authentication and backend routes are unchanged.

This is a sales prototype, not a working customer installation. All state lives in React memory and disappears on refresh. It makes no API calls, stores no data, sends no messages and uses no AI model or connected calendar. Use fictional details only. Piper and telephone integration are not implemented here.

## Run

From `apps/web`:

```sh
npm ci
npm run build
npx next start -p 3107
```

Open http://localhost:3107/demo. This local URL is not a public tester link.

## Verify

```sh
npm run lint
npm run typecheck
npm run test:unit
npm run build
npx playwright test --config playwright.demo.config.ts
```

Install the matching Playwright browser if needed, or set `PW_CHROMIUM_PATH` to an existing compatible Chromium binary. The demo tests require neither an API server nor a database. They check approval after editing, duplicate-decision prevention, refresh/reset, decline, form validation, mobile width and absence of API traffic. Existing backend-dependent e2e tests remain unchanged.

## External testing

No app account is required for `/demo`, but Vercel's deployment protection applies before the app. A protected preview will still show Vercel login. Once publishing is explicitly authorized, use a share link for the deployment or a separate public demo-only deployment. Do not disable authentication on the operator API. Never claim the new demo is live merely because the old pilot's deployment exists.

## Production follow-up

Use existing tenant intake and approvals for the actual product. A callback must be modeled explicitly rather than misrepresented as a confirmed engineer visit. Add server validation, idempotency, tenant access checks, audit events, persistence and a customer-authorized delivery channel before accepting real enquiries. Verify in an isolated test tenant first.
