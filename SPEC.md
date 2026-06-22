# Todo App Specification

## 1. Project Overview
- **Project Name**: Zen Tasks
- **Type**: Single-page web application
- **Core Functionality**: A minimalist, elegant todo list app with add, complete, delete, and filter capabilities
- **Target Users**: Anyone who wants a clean, distraction-free task management experience

## 2. UI/UX Specification

### Layout Structure
- **Container**: Centered card (max-width: 480px) with generous padding
- **Header**: App title with subtle tagline
- **Input Section**: Text input + add button in a horizontal row
- **Filter Tabs**: All / Active / Completed as pill-style buttons
- **Todo List**: Scrollable list area with individual todo items
- **Footer**: Shows remaining active count

### Visual Design

#### Color Palette
- **Background**: `#1a1a2e` (deep navy)
- **Card Background**: `#16213e` (dark blue)
- **Primary Accent**: `#e94560` (coral red)
- **Secondary Accent**: `#0f3460` (muted blue)
- **Text Primary**: `#eaeaea` (off-white)
- **Text Secondary**: `#7f8c8d` (muted gray)
- **Success**: `#00d9a5` (mint green)
- **Danger**: `#ff6b6b` (soft red)
- **Completed Text**: `#5a6270` (gray)

#### Typography
- **Font Family**: 'Outfit' (Google Fonts) - modern geometric sans-serif
- **Title**: 28px, weight 700
- **Tagline**: 14px, weight 400, text-secondary
- **Input**: 16px, weight 400
- **Todo Text**: 16px, weight 500
- **Filter Tabs**: 13px, weight 600, uppercase, letter-spacing 0.5px
- **Footer**: 13px, weight 400

#### Spacing
- **Card Padding**: 32px
- **Section Gap**: 24px
- **Todo Item Padding**: 16px vertical, 0 horizontal
- **Border Radius**: Card 16px, Buttons 8px, Inputs 8px

#### Visual Effects
- **Card Shadow**: 0 25px 50px -12px rgba(0, 0, 0, 0.5)
- **Input Focus**: 2px solid primary accent with glow
- **Button Hover**: Scale 1.05 with brightness increase
- **Todo Hover**: Background lighten slightly
- **Checkbox Animation**: Smooth scale + color transition (0.2s)
- **Delete Animation**: Fade out + slide right (0.3s)
- **Add Animation**: Fade in + slide down (0.3s)

### Components

#### Input Section
- Text input with placeholder "Add a new task..."
- Add button with "+" icon
- Input has subtle inner shadow
- Button has gradient background (primary accent)

#### Filter Tabs
- Three pill buttons: All, Active, Completed
- Active tab has filled background with primary accent
- Inactive tabs are transparent with border

#### Todo Item
- Custom circular checkbox (unchecked: border only, checked: filled with checkmark)
- Task text (strikethrough when completed)
- Delete button (trash icon) appears on hover
- Checkbox and delete have smooth transitions

#### Empty State
- Shows a friendly message when no todos exist
- Subtle illustration or icon

## 3. Functionality Specification

### Core Features
1. **Add Todo**: Enter text in input, press Enter or click Add button
2. **Complete Todo**: Click checkbox to toggle completion status
3. **Delete Todo**: Click delete icon to remove todo
4. **Filter Todos**: Click tabs to filter by All/Active/Completed
5. **Persistence**: Save todos to localStorage

### User Interactions
- Pressing Enter in input adds the todo
- Empty input shows subtle shake animation (no add)
- Completed todos show strikethrough text
- Filter shows count badge on each tab
- Footer shows "X tasks left" dynamically

### Data Handling
- Store todos as JSON array in localStorage
- Each todo: { id: timestamp, text: string, completed: boolean }
- Load todos on page load
- Save on every change

### Edge Cases
- Empty text: Don't add, show shake animation
- Very long text: Truncate with ellipsis
- No todos: Show empty state message
- All completed: Show "All done!" message

## 4. Acceptance Criteria

### Visual Checkpoints
- [ ] Dark theme with coral accent is visible
- [ ] Card is centered with proper shadow
- [ ] Outfit font is loaded and applied
- [ ] Input has focus glow effect
- [ ] Filter tabs show active state correctly
- [ ] Checkbox animates on toggle
- [ ] Delete button appears on hover

### Functional Checkpoints
- [ ] Can add a new todo
- [ ] Can mark todo as complete/incomplete
- [ ] Can delete a todo
- [ ] Filter tabs work correctly
- [ ] Todos persist after page refresh
- [ ] Empty input doesn't create todo
- [ ] Footer shows correct count
