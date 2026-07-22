# P4-6: TUI Settings Tab

## Problem
The Textual TUI has no visual settings interface. Users must edit YAML files or
use the CLI to change config (theme, model, provider, temperature). This makes
the TUI feel incomplete — a settings screen is the natural counterpart to the
session list screen added in Iteration 12.

## Requirements
1. New "Settings" screen accessible via F3 keybinding
2. Display current config fields in editable widgets
3. Editable fields: provider, model, temperature, theme, system_prompt
4. Save button to persist changes
5. Cancel/Escape to discard and return

## Acceptance Criteria
- [ ] Settings screen renders with current config values
- [ ] Fields are editable (Input for text, Input for numbers with validation)
- [ ] Save updates config and pop screen
- [ ] Cancel discards changes
- [ ] Escape returns without changes
- [ ] Validation: temperature 0.0–2.0, model non-empty

## Implementation Plan
1. Write tests for SettingsScreen
2. Implement SettingsScreen with form-like layout
3. Wire F3 keybinding in CScodeTUI
4. Verify with pilot tests
