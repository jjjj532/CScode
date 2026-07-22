# TUI Input Autocomplete

## Problem
TUI users type commands like `/sessions`, `/new`, `/switch`, `/tab` manually with no discovery or completion. They must remember exact syntax.

## Solution
Add Tab-key autocomplete to the TUI chat Input widget:
- Type `/` + partial command → press Tab → cycles through matching commands
- Completion shows in a hint label below the input
- Repeated Tab cycles through matches
- Enter/Space accepts the current suggestion
- Escape cancels completion

## Known Commands
| Command | Aliases |
|---------|---------|
| `/sessions` | `/s` |
| `/new` | `/n` |
| `/switch <id>` | — |
| `/kill <id>` | `/delete` |
| `/tab list` | — |
| `/tab create <mode>` | — |
| `/tab switch <id>` | — |
| `/tab close <id>` | — |
| `/help` | `/h` |
| `/quit` | `/exit`, `/q` |

## Acceptance Criteria
1. Pressing Tab when input starts with `/` shows completions
2. `/s` → Tab → cycles: `/s` → `/sessions` → `/switch`
3. `/n` → Tab → cycles: `/n` → `/new`
4. Repeated Tab cycles forward through matches
5. Pressing Tab when input doesn't start with `/` does nothing
6. After completion, typing continues normally
7. Escape cancels active completion
8. All behavior has tests
