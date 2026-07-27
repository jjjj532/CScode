# Spec: Frontend Offline Detection + Auto-Retry

## Objective
Detect network interruptions and provide graceful degradation. Currently when the backend server goes down or network is lost, users see blank data, stale UI, or silent failures with no explanation.

## Success Criteria
- [ ] `useOnlineStatus` hook returns `isOnline` boolean reactive to `online`/`offline` events
- [ ] `OfflineBanner` component shows a visible banner when offline, auto-hides when back online
- [ ] Failed API requests in `api.ts` auto-retry with exponential backoff (max 3 attempts)
- [ ] Toast notification fires on reconnection ("Back online")
- [ ] All tests pass: `npm test` (0 failures)

## Commands
```bash
npm test
npx jest --no-cache --verbose __tests__/useOnlineStatus.test.tsx
```

## Files
```
NEW: src/cscode/web/src/hooks/useOnlineStatus.ts     # Hook
NEW: src/cscode/web/src/components/ui/OfflineBanner.tsx  # Banner
NEW: __tests__/useOnlineStatus.test.tsx               # Hook tests
NEW: __tests__/OfflineBanner.test.tsx                 # Banner tests
MOD: src/cscode/web/src/App.tsx                       # Add OfflineBanner
MOD: src/cscode/web/src/lib/api.ts                    # Auto-retry logic
```

## Code Style
- Hook: Single `useSyncExternalStore` or `useState` + `useEffect`
- Banner: Tailwind yellow/warning theme
- Retry: Exponential backoff (1s, 2s, 4s max 3 attempts)

```tsx
// Example hook signature
export function useOnlineStatus(): boolean {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  useEffect(() => {
    const goOnline = () => setIsOnline(true);
    const goOffline = () => setIsOnline(false);
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, []);
  return isOnline;
}
```

## Testing Strategy
| Test | Type | Verifies |
|------|------|----------|
| useOnlineStatus returns boolean | Unit | Hook contract |
| useOnlineStatus reacts to events | Unit | Event listener setup |
| OfflineBanner renders when offline | Integration | Visibility |
| OfflineBanner hidden when online | Integration | Correct state |
| App.tsx includes OfflineBanner | Integration | Rendering |

## Boundaries
- **Always:** Use `navigator.onLine` as source of truth
- **Ask first:** Adding npm dependencies for offline support
- **Never:** Polling server health as substitute for browser events
