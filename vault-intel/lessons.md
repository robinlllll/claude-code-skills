# vault-intel lessons

## 2026-02-12 | Hyphen in skill folder name breaks Python imports

Skill folders use hyphens (`vault-intel`, `cross-13f`, `vault-health`) per convention, but Python cannot import modules with hyphens in the name. `from vault_intel.scripts.config import ...` fails because the directory is `vault-intel`.

**Fix:** Don't use the skills dir as a package root. Instead, each script adds its own `scripts/` directory to `sys.path` and imports siblings directly:
```python
SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
from config import load_config
```
For cross-skill imports (e.g. `shared.task_manager`), add the skills dir separately:
```python
SKILLS_DIR = r"C:\Users\thisi\.claude\skills"
if SKILLS_DIR not in sys.path:
    sys.path.insert(0, SKILLS_DIR)
```
This pattern works for any hyphenated skill folder. Never rely on dotted package imports through hyphenated directories.
