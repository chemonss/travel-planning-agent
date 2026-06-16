"""
Загрузчики данных оценки: Q&A-кейсы и reference-рекомендации.

Делает данные оценки доступными как Python-объекты без ручного копирования из
файлов (нормализует `expected_outcome_type` и `expected_entities`).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_QA_PATH = _PROJECT_ROOT / "data" / "qa" / "qa.jsonl"
DEFAULT_REFERENCE_DIR = _PROJECT_ROOT / "data" / "reference"


def load_qa_cases(path: Path | str = DEFAULT_QA_PATH) -> list[dict[str, Any]]:
    """Загружает и нормализует Q&A-кейсы из qa.jsonl."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"QA dataset not found: {path}")

    cases: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            cases.append(
                {
                    "case_id": raw.get("case_id"),
                    "category": raw.get("category"),
                    "group_id": raw.get("group_id"),
                    "input_channel": raw.get("input_channel"),
                    "user_request": raw.get("user_request", ""),
                    "expected_outcome_type": raw.get("expected_outcome_type"),
                    "expected_entities": raw.get("expected_entities") or {},
                    "notes": raw.get("notes", ""),
                }
            )
    return cases


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_reference(reference_dir: Path | str = DEFAULT_REFERENCE_DIR) -> dict[str, Any]:
    """Загружает эталонные рекомендации по перелётам и отелям.

    @return Словарь с ключами `flights`, `hotels` (списки строк CSV) и
        `by_group` (рекомендованные flight_id/hotel_id по group_id).
    """
    reference_dir = Path(reference_dir)
    flights = _read_csv(reference_dir / "flight_recommendations.csv")
    hotels = _read_csv(reference_dir / "hotel_recommendations.csv")

    by_group: dict[str, dict[str, str]] = {}
    for row in flights:
        by_group.setdefault(row["group_id"], {})["flight_id"] = row.get("recommended_flight_id", "")
    for row in hotels:
        by_group.setdefault(row["group_id"], {})["hotel_id"] = row.get("recommended_hotel_id", "")

    return {"flights": flights, "hotels": hotels, "by_group": by_group}
