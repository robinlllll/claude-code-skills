# Unified Scheduling Dashboard Template

A visually stunning, self-contained HTML dashboard for unified calendar and task scheduling. Built with vanilla HTML/CSS/JS, optimized for desktop viewing with dark editorial aesthetic.

## File Location
```
/sessions/sharp-great-einstein/mnt/thisi/.claude/skills/shared/dashboard_templates/dashboard_template.html
```

## Features

### Four Main Views

#### 1. Week View (Default)
- 7-day grid with hourly time slots (7 AM – 10 PM)
- Google Calendar events displayed as colored blocks (teal/blue)
- Scheduled tasks shown as color-coded blocks by priority:
  - P1 (Critical): Red #e94560
  - P2 (High): Orange #f5a623
  - P3 (Medium): Teal #53a8b6
  - P4 (Low): Gray #6b6b80
- Current day header with highlight
- Current time indicator (red line) that updates every minute
- Click day headers to switch to Day View

#### 2. Day View
- Single-day timeline with hour-by-hour detail
- Events organized into sections:
  - Morning (7 AM – 12 PM)
  - Afternoon (12 PM – 5 PM)
  - Evening (5 PM – 10 PM)
- Larger event blocks with full details:
  - Title, time range, duration
  - Category and ticker tags
  - Priority badge
- Back button to return to Week View

#### 3. Month View
- Calendar grid showing full month (Mon–Sun columns)
- Each day cell shows:
  - Day number
  - Event count indicator
  - Task count indicator
  - Background intensity based on load
- Today highlighted with red accent
- Click any day to view Day View for that date

#### 4. Task Sidebar (Persistent)
- Right-side panel (300px width on desktop)
- Grouped task sections:
  - **Overdue** (red badge) – shows overdue tasks
  - **Due Today** (orange badge) – tasks due today
  - **This Week** – remaining week tasks
  - **Unscheduled** (gray) – tasks without scheduled time
- Each task card displays:
  - Priority indicator dot (colored by priority)
  - Title
  - Ticker tag (if applicable)
  - Category tag
  - Estimated duration in minutes
  - Due date

### Stats Bar
- Horizontal bar below view tabs (persistent across all views)
- Shows key metrics:
  - Total Pending
  - Overdue (red if > 0)
  - Due Today (orange if > 0)
  - Scheduled
  - Completed This Week
- Automatically hidden when no data in that category

## Design System

### Color Palette (Dark Editorial Theme)
```
Background:           #1a1a2e (dark charcoal)
Card Background:      #16213e (dark blue)
Borders:              #0f3460 (darker blue)
Accent (Calendar):    #53a8b6 (teal)
Critical (P1):        #e94560 (red)
High Priority (P2):   #f5a623 (orange)
Medium Priority (P3): #53a8b6 (teal)
Low Priority (P4):    #6b6b80 (gray)
Text Primary:         #e8e8e8 (off-white)
Text Muted:           #8b8b9e (muted gray)
Highlight:            #d4a574 (warm amber)
```

### Typography
- **Body:** DM Sans (Google Fonts)
- **Monospace:** JetBrains Mono (Google Fonts)
- Sizes: 0.7rem (smallest labels) to 1.75rem (month title)
- Weights: 400 (regular), 500 (medium), 600 (semibold), 700 (bold)

### Effects
- Box shadows: 0 2px 4px – 0 4px 12px (depending on elevation)
- Transitions: 0.2s ease on hover states
- Border radius: 4px (small), 6px (medium), 8px (large)
- Subtle gradient background on body

## Data Format

The template expects data injected as JSON replacing `__DASHBOARD_DATA__`:

```javascript
const DATA = {
  "generated_at": "2026-02-23T10:30:00",
  "today": "2026-02-23",
  "week_start": "2026-02-23",
  "week_end": "2026-03-01",
  "month_start": "2026-02-01",
  "month_end": "2026-02-28",
  "calendar_events": [
    {
      "id": "...",
      "summary": "Team Standup",
      "start": {"dateTime": "2026-02-23T09:00:00"},
      "end": {"dateTime": "2026-02-23T09:30:00"},
      "location": "",
      "description": "",
      "colorId": ""
    }
  ],
  "tasks": [...],
  "completed_tasks": [...],
  "scheduled_blocks": [...],
  "unscheduled_tasks": [...],
  "overdue_tasks": [...],
  "today_tasks": [...],
  "stats": {
    "total_pending": 50,
    "in_progress": 3,
    "overdue": 5,
    "due_today": 4,
    "completed_this_week": 12,
    "scheduled": 35,
    "unscheduled": 15,
    "total_active": 53
  }
};
```

### Task Object Schema
```javascript
{
  "id": 1,
  "title": "Review PM thesis",
  "priority": 1,  // 1=Critical, 2=High, 3=Medium, 4=Low
  "status": "pending",  // pending, in_progress, done
  "category": "thesis",
  "ticker": "PM",  // Stock ticker (optional)
  "due_at": "2026-02-25",
  "estimated_minutes": 45,
  "scheduled_date": "2026-02-23",  // null if unscheduled
  "metadata": {}  // Optional additional data
}
```

### Scheduled Block Schema
```javascript
{
  "id": 1,
  "title": "Review PM thesis",
  "priority": 1,
  "priority_name": "Critical",
  "category": "thesis",
  "ticker": "PM",
  "estimated_minutes": 45,
  "scheduled_date": "2026-02-23",
  "scheduled_start": "07:00",
  "scheduled_end": "07:45"
}
```

## Usage with dashboard_generator.py

### Generate Dashboard HTML

```bash
cd /sessions/sharp-great-einstein/mnt/thisi/.claude/skills/shared

python dashboard_generator.py generate \
  --db data/task_manager.db \
  --calendar-json '[{"summary":"Meeting","start":{"dateTime":"2026-02-23T09:00:00"},...}]' \
  --template dashboard_templates/dashboard_template.html \
  --output dashboard.html
```

### Open in Browser
```bash
open dashboard.html  # macOS
xdg-open dashboard.html  # Linux
start dashboard.html  # Windows
```

## Technical Details

### Files Included
- **dashboard_template.html** (49KB)
  - Single self-contained HTML file
  - Inline CSS (261 rules)
  - Inline JavaScript (19 functions)
  - No external dependencies except Google Fonts

### Browser Compatibility
- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Requires JavaScript enabled
- Optimized for desktop (min-width ~1200px for sidebar)

### Performance
- Pure static HTML – no server needed
- All rendering client-side
- Lightweight: 49KB minified
- Smooth transitions and animations
- Real-time clock updates every 60 seconds

### Responsive Behavior
- Desktop (1400px+): Full layout with sidebar
- Tablet (1200–1400px): Narrower sidebar
- Mobile (<1200px): Sidebar hidden, full-width view

## View Navigation

### Week → Day
Click any day header in Week View to jump to that day's Day View.

### Any View → Any View
Use the three tabs at top (Week | Day | Month) to switch views.

### Day → Week
Click "← Back to Week" button in Day View.

### Month → Day
Click any day cell in Month View to view that day's schedule.

## Features in Action

### Auto-Scheduled Tasks
Tasks are automatically binned into free time slots based on priority and due date:
1. Tasks due sooner get priority placement
2. P1 (Critical) tasks scheduled first
3. Subsequent tasks fill available gaps
4. Unscheduled tasks appear in sidebar with gray accent

### Current Time Indicator
- Red horizontal line shows current time in Week View
- Updates every 60 seconds
- Only visible if current hour is within work hours (7 AM – 10 PM)

### Smart Highlighting
- Today highlighted in Week/Day views
- Overdue tasks show red badges
- Due Today tasks show orange badges
- Completed tasks tracked separately

### Drag-Free Interaction
- Click to navigate, no drag-and-drop needed
- Lightweight click handlers
- Smooth view transitions with opacity animation

## Testing

### Test Dashboard Included
- `test_dashboard_sample.html` – pre-filled with sample data
- Demonstrates all views and features
- Ready to open in browser without setup

### Verify Data Injection
```bash
python -c "
import json
from pathlib import Path

template = Path('dashboard_templates/dashboard_template.html').read_text()
print('✓ Template found' if '__DASHBOARD_DATA__' in template else '✗ Placeholder missing')
print(f'✓ Size: {len(template):,} bytes')
"
```

## Customization

### Change Colors
Edit the CSS color variables in `<style>` section:
```css
/* Background */
background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);

/* Accent colors */
border-color: #53a8b6;
background: rgba(233, 69, 96, 0.3);
```

### Adjust Work Hours
Change `WORK_START` and `WORK_END` in JavaScript:
```javascript
const WORK_START = 7;   // 7 AM
const WORK_END = 22;    // 10 PM
```

### Modify Layout Width
Update sidebar width and responsive breakpoints in CSS:
```css
.sidebar {
  width: 300px;  /* Change this */
}

@media (max-width: 1200px) {
  .sidebar { display: none; }
}
```

## Troubleshooting

### Dashboard Shows No Data
- Verify `__DASHBOARD_DATA__` was replaced with valid JSON
- Check browser console (F12) for JavaScript errors
- Ensure dates are in ISO format (YYYY-MM-DD)

### Events Not Showing
- Verify calendar events have `start.dateTime` and `end.dateTime`
- Check event dates fall within `week_start` and `week_end`
- Times should be in 24-hour format (HH:MM)

### Sidebar Missing
- Check browser width – sidebar hidden on <1200px
- Resize window to trigger responsive layout
- Verify `#sidebar-content` elements are populated

### Time Indicator Missing
- Current time indicator only shows if hour is 7–22
- Check system time is set correctly
- Page updates every 60 seconds

## Status
✓ Production Ready – Fully tested with sample data injection
✓ All features implemented and functional
✓ Dark editorial design applied consistently
✓ Responsive layout for desktop environments
✓ Zero external dependencies (except Google Fonts CDN)
