# P4-5: TUI Session List

## Problem
The Textual TUI currently has no session management view. Users cannot browse,
select, or manage their chat sessions from within the terminal UI. They must use
the CLI (`cs session list`) or web UI to view sessions.

## Requirements
1. New "Sessions" screen accessible from the TUI sidebar/menu
2. Display sessions in a paginated list (20 per page)
3. Each row shows: session ID (short), message count, last activity time, status
4. Pagination via "Load More" button or scroll-to-bottom
5. Selecting a session opens/reloads it in the chat view
6. Data source: `GET /api/sessions` endpoint (already exists)

## Acceptance Criteria
- [ ] Session list screen renders with correct data
- [ ] Pagination works (load more pages)
- [ ] Selecting a session navigates to chat view
- [ ] Empty state shown when no sessions exist
- [ ] Loading state shown while fetching
- [ ] Error state shown on API failure

## Implementation Plan
1. Add `SessionsScreen` widget (Textual Screen)
2. Add session list data table with columns
3. Wire pagination (offset/limit)
4. Wire navigation → chat screen on select
5. Add sidebar menu entry
6. Write tests
