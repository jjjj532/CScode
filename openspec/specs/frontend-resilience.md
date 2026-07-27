# Spec: Frontend Resilience — Skeleton Loading + Error Handling

## Objective
Eliminate blank flashes and silent failures in the React web UI. Currently:
- `App.tsx` fetches `/api/config` and `/api/sessions` with `.catch(() => {})` — errors swallowed silently
- No loading indicator during initial data fetch (users see blank sidebar + empty content)
- No retry mechanism for failed fetches
- `useConfigStore.loading` defined but never set to `true`

Success: All data fetches show skeleton while loading, toast errors on failure, and auto-retry on initial load.

## Tech Stack
- React 18 + TypeScript + Tailwind CSS (v3)
- Zustand 5 for state management
- Jest 29 + React Testing Library 14 for tests
- Lucide React for icons

## Commands
```bash
# Test (in src/cscode/web/)
npm test

# Run single test
npx jest --verbose --no-cache __tests__/Skeleton.test.tsx

# Lint
npx tsc --noEmit

# Dev
npm run dev
```

## Project Structure (web)
```
src/cscode/web/src/
  components/ui/        → Shared UI components (existing)
    Skeleton.tsx         → NEW: Reusable skeleton building block
    ErrorBoundary.tsx    → Existing
    ToastContainer.tsx   → Existing
  stores/               → Zustand stores
    useConfigStore.ts    → Existing: has `loading` field
    useSessionStore.ts   → Existing: has `sessionLoading`
    useToastStore.ts     → Existing: addToast/removeToast
  lib/
    api.ts              → Existing: has `request()` with error throw
__tests__/              → Test files
```

## Code Style
- Functional components with hooks
- Tailwind utility classes (no CSS modules)
- TypeScript strict — no `any` types
- zustand stores with selector pattern
- Jest mocks for stores: `jest.mock('../src/stores/useXxxStore')`

Example Skeleton component pattern:
```tsx
// Skeleton: animated placeholder
export function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse bg-v2-bg-deep rounded ${className ?? ''}`} role="status" aria-label="Loading" />;
}
```

## Testing Strategy
| Level | Tool | Coverage |
|-------|------|----------|
| Unit (Component) | Jest + RTL | Skeleton renders with correct classes |
| Unit (Store) | Jest + renderHook | Loading state toggles correctly |
| Integration | Jest + RTL | App.tsx shows skeleton during fetch, toast on error |

Tests follow DAMP pattern: mock stores, render component, assert behavior.

## Boundaries
- **Always:** Set `loading=true` before fetch, `loading=false` after; show toast on errors
- **Ask first:** Adding new npm dependencies, changing test framework, touching backend
- **Never:** Silent `.catch(() => {})` — all errors must show toast or fallback UI

## Success Criteria
- [ ] `Skeleton` component renders animated placeholder with `role="status"`
- [ ] `App.tsx` sets `useConfigStore.loading=true` during `/api/config` fetch
- [ ] Sidebar shows skeleton items while sessions load
- [ ] Fetch failures show error toast (not silent swallow)
- [ ] All existing tests still pass
- [ ] `npm test` passes with 0 failures

## Open Questions
- None — scope well-understood from codebase analysis.

---

# Implementation Plan

## Architecture Decisions
- **Skeleton as building block**: One `Skeleton` component with className prop, consumed by `App.tsx` and `Sidebar` inline.
- **No retry library**: Use simple `setTimeout` retry (3 attempts, 1s backoff) — minimal dependency.
- **Toast for errors**: Use existing `useToastStore.addToast(message, 'error')` — no new notification system.

## Task List

### Phase 1: Skeleton Component
- [ ] **Task 1: `Skeleton` + `SkeletonList` components** — Reusable animated placeholder primitives
  - `src/cscode/web/src/components/ui/Skeleton.tsx`
  - `__tests__/Skeleton.test.tsx`

### Phase 2: Loading States (App.tsx + Sidebar)
- [ ] **Task 2: Wire loading state in App.tsx** — Set `loading=true/false` around config fetch, show skeleton UI
  - `src/cscode/web/src/App.tsx`
  - `__tests__/App.test.tsx`

- [ ] **Task 3: Wire loading state in Sidebar** — Show skeleton items while sessions load
  - No code changes needed — Sidebar already has empty state. Sessions fetch is in `useEffect` with `.catch()`. Add loading indicator.

### Phase 3: Error Handling + Retry
- [ ] **Task 4: Fetch error handling** — Replace `.catch(() => {})` with toast + retry in App.tsx
  - `src/cscode/web/src/App.tsx`

### Checkpoint: Verify
- [ ] `npm test` passes
- [ ] `npx tsc --noEmit` passes
- [ ] Manual verification of skeleton loading + error toast

## Files Likely Touched
- `src/cscode/web/src/components/ui/Skeleton.tsx` (NEW)
- `src/cscode/web/src/App.tsx`
- `src/cscode/web/src/components/layout/Sidebar.tsx`
- `src/cscode/web/__tests__/Skeleton.test.tsx` (NEW)
- `src/cscode/web/__tests__/App.test.tsx` (NEW)
- `src/cscode/web/src/lib/api.ts` (minor — add retry helper)

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| `loading` state not propagating to UI due to zustand selector scope | Med | Use `useConfigStore(s => s.loading)` directly in App.tsx |
| Toast from App.tsx fails if useToastStore not initialized | Low | useToastStore is always initialized (no async init) |

## Verification Plan
```
Phase 1 complete → npm test (Skeleton tests pass)
Phase 2 complete → npm test (App test passes, no regressions)
Phase 3 complete → npm test (all pass), npx tsc --noEmit
```
