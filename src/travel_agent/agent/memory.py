"""
Долгосрочная память агента — «цифровой двойник» сессии/группы.

Внешнее по отношению к агенту хранилище (`data/memory/<session>.json`), куда агент
сам решает сохранять важные факты, уточнения и принятые планы, чтобы возвращаться
к ним на следующих ходах диалога (многоходовость). Читается через `recall`,
пополняется через `append` (заметки модели) и `save_plan` (итоговые решения).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MEMORY_DIR = _PROJECT_ROOT / "data" / "memory"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_session(session_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", session_id) or "default"


class MemoryStore:
    """Файловое хранилище долгосрочной памяти по сессиям."""

    def __init__(self, base_dir: Path | str = DEFAULT_MEMORY_DIR) -> None:
        self.base_dir = Path(base_dir)

    def _path(self, session_id: str) -> Path:
        return self.base_dir / f"{_safe_session(session_id)}.json"

    def recall(self, session_id: str) -> dict[str, Any]:
        """Возвращает сохранённое состояние сессии (заметки и планы)."""
        path = self._path(session_id)
        if not path.exists():
            return {"notes": [], "plans": []}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"notes": [], "plans": []}

    def _write(self, session_id: str, data: dict[str, Any]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._path(session_id).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def append(self, session_id: str, content: str) -> None:
        """Добавляет текстовую заметку (решение модели запомнить факт)."""
        data = self.recall(session_id)
        data.setdefault("notes", []).append({"ts": _now(), "content": content})
        self._write(session_id, data)

    def save_plan(self, session_id: str, plan: dict[str, Any]) -> None:
        """Сохраняет итоговый план/решение хода (структурно)."""
        data = self.recall(session_id)
        data.setdefault("plans", []).append({"ts": _now(), **plan})
        self._write(session_id, data)

    def clear(self, session_id: str) -> None:
        path = self._path(session_id)
        if path.exists():
            path.unlink()
