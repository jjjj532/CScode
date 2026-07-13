# Fix CredentialPanel password form wrapper

## Problem
Browser console warning: `[DOM] Password field is not contained in a form` and `Input elements should have autocomplete attributes` for the API key input in CredentialPanel.tsx.

## Expected Behavior
- Password input in CredentialPanel is wrapped in `<form onSubmit={(e) => e.preventDefault()}>`
- No browser accessibility warnings for this password field
- `autoComplete="off"` attribute present

## Acceptance Criteria
- [ ] CredentialPanel password input wrapped in `<form>` with `onSubmit={(e) => e.preventDefault()}`
- [ ] `autoComplete="off"` attribute added to password input
- [ ] Existing functionality preserved (adding/removing credentials works)
- [ ] No new console warnings

## Implementation
1. Wrap the password input + its container in `<form onSubmit={(e) => e.preventDefault()}>`
2. Add `autoComplete="off"` to the password input
