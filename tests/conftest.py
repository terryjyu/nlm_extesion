import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

# Prefer src-layout imports during local test runs.
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Keep repo root available for top-level modules (e.g. export_automation.py).
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
