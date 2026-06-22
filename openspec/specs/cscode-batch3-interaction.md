# Batch 3: Interaction System (交互系统)

## Overview
Improve the GUI interaction layer: toast notifications, settings panel UX,
session rename, file attachment display, and unified error handling.

## Tasks

### 3.1 Toast notification system
Zustand store + container component. Used by all subsequent tasks.
- `useToastStore` with `addToast(msg, type, duration)` and auto-dismiss
- `ToastContainer` rendered in App.tsx with stacking

### 3.2 Settings panel UX
- Show error toast on save failure (instead of console.error)
- Escape key closes settings panel

### 3.3 Session rename
- Inline rename in ProjectItem (click title → edit mode)
- Calls `PATCH /api/sessions/{id}` backend endpoint
- Updates store on success

### 3.4 File attachment improvements
- Show file size next to filename
- Different icons per file type (code, image, doc, generic)

### 3.5 Unified error handling
- Stream errors surfaced via toast (not just console.error)
- Session create/delete errors via toast
- Config load errors via toast
