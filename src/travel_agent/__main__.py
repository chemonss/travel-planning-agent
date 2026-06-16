"""Позволяет запускать агента как `python -m travel_agent`."""

import sys
from pathlib import Path

# Гарантируем доступность корня проекта (prompts/, data/) при запуске как модуль.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT))

from main import main  # noqa: E402

if __name__ == "__main__":
    main()
