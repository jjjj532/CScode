# TUI Session Detail Screen

## Problem
TUI users can list sessions (F2 → SessionsScreen) but have no way to view a session's full details or messages without switching to it and checking the main chat area.

## Solution
Add a `SessionDetailScreen` — a read-only detail view for a single TUI session that shows:
- Session metadata (title, ID, provider, model, status, timestamps)
- Session messages in a scrollable `RichLog`
- The active session indicator

## Acceptance Criteria
1. Pressing Enter on a session row in `SessionsScreen` pushes the detail screen
2. Detail screen shows session metadata (title, ID, provider, model, status, created_at)
3. Detail screen shows session messages with role labels (user / assistant / system)
4. `escape` returns to SessionsScreen
5. `d` deletes the session (with confirmation)
6. Empty session shows a "No messages" placeholder
7. TuiSession gains a `messages` field to support message storage
8. All new code has tests

## Key Bindings
| Key | Action |
|-----|--------|
| `escape` | Back to SessionsScreen |
| `d` | Delete session (TBD: confirmation dialog) |

## Wire Flow
```
SessionsScreen (F2)
  └─ enter on row → push_screen(SessionDetailScreen)
      └─ escape → pop_screen back to SessionsScreen
      └─ d → confirm → remove session → pop_screen to SessionsScreen
```
