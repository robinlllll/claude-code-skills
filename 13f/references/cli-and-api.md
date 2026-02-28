# 13F — CLI Commands, Programmatic API & Email Delivery

## AI Analysis Workflow

### One-command (recommended)
```bash
python ai_analyzer.py MANAGER_FOLDER 2025-Q3 --model all --obsidian
# Output: gemini vN.md, grok vN.md, synthesis vN.md → all in Obsidian
```

### Programmatic (from Python / Claude Code)
```python
import sys
sys.path.insert(0, r'C:\Users\thisi\13F-CLAUDE')
from ai_analyzer import (
    load_manager_data, get_available_managers,
    run_two_stage_analysis, find_latest_obsidian_analysis,
    run_synthesis, save_to_obsidian,
)

data = load_manager_data('MANAGER_FOLDER', '2025-Q3')

# Step 1-2: Run Gemini + Grok 2-stage
run_two_stage_analysis(data, model='gemini', obsidian=True, folder_name='MANAGER_FOLDER')
run_two_stage_analysis(data, model='grok', obsidian=True, folder_name='MANAGER_FOLDER')

# Step 3: Synthesis (reads latest Obsidian outputs)
manager_name = data.get('name', 'MANAGER_FOLDER')
gp = find_latest_obsidian_analysis(manager_name, '2025-Q3', 'gemini')
kp = find_latest_obsidian_analysis(manager_name, '2025-Q3', 'grok')
run_synthesis(gp.read_text(encoding='utf-8'), kp.read_text(encoding='utf-8'), manager_name, '2025-Q3')
```

### Generate dashboard chart (optional)
```python
from position_chart import generate_dashboard
generate_dashboard('MANAGER_FOLDER')
# Saves dashboard.png to manager's Obsidian folder
```

## CLI Commands

```bash
# Full 3-step pipeline (recommended): Gemini + Grok + Synthesis → Obsidian
python ai_analyzer.py BERKSHIRE_HATHAWAY_INC_1067983 2025-Q3 --model all --obsidian

# Same, with email delivery (uses EMAIL_DEFAULT_RECIPIENTS from .env)
python ai_analyzer.py BERKSHIRE_HATHAWAY_INC_1067983 2025-Q3 --model all --obsidian --email

# Email to specific recipients
python ai_analyzer.py BERKSHIRE_HATHAWAY_INC_1067983 2025-Q3 --model all --obsidian --email-to "alice@example.com,bob@example.com"

# Single model only (no synthesis)
python ai_analyzer.py BERKSHIRE_HATHAWAY_INC_1067983 2025-Q3 --model gemini --obsidian
python ai_analyzer.py BERKSHIRE_HATHAWAY_INC_1067983 2025-Q3 --model grok --obsidian

# Legacy single-stage mode
python ai_analyzer.py BERKSHIRE_HATHAWAY_INC_1067983 2025-Q3 --model gemini --single-stage

# List available managers
python ai_analyzer.py --list 2025-Q3

# Cross-holdings analysis (stocks held by 3+ managers)
python ai_analyzer.py --cross 2025-Q3 --model all

# Build history for all managers (run before analysis)
python history_builder.py --all

# Generate charts for a manager
python position_chart.py MANAGER_FOLDER
```

## Email Delivery

Add `--email` to send analysis via email after completion. For `--model all`, the synthesis report is emailed; for single model, that model's output is sent. Dashboard chart attached if available.

Requires `EMAIL_USER` and `EMAIL_APP_PASSWORD` in `~/Screenshots/.env`. Uses Gmail SMTP by default.

## AI Analysis Engines

| Engine | Role | API Key |
|--------|------|---------|
| Gemini | 量化叙事、配对逻辑 | GEMINI_API_KEY in .env |
| Grok | 逆向思维、市场结构 + Synthesis | XAI_API_KEY in .env |

**Note:** Claude and ChatGPT models are deprecated for 13F analysis. Use `--model all` (Gemini + Grok + Synthesis).
