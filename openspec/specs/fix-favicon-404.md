# Fix favicon 404

## Problem
Browser auto-requests `/favicon.ico`, returns 404 because no favicon file exists in the project.

## Expected Behavior
- `GET /favicon.ico` returns 200 with a valid favicon image
- No 404 in browser console

## Acceptance Criteria
- [ ] A favicon.ico file exists in `src/cscode/web/public/` (copied to dist by Vite)
- [ ] `index.html` references it with `<link rel="icon">`
- [ ] `GET /favicon.ico` returns 200 during dev and production
- [ ] Manual: no 404 network error in browser devtools

## Implementation
1. Generate a simple 32x32 favicon.ico from the existing app icon PNG
2. Place it in `src/cscode/web/public/` (Vite auto-copies public/ to dist)
3. Add `<link rel="icon" type="image/x-icon" href="/favicon.ico">` to `index.html`
