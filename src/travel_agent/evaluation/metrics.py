"""
Метрики E2E-оценки.

Считает качество отдельно по типам задач (README): корректность исхода, точность
сущностей (перелёт/отель/тур), корректность эскалации и разбивку по категориям.
Сравнение строго структурное — без парсинга свободного текста и без LLM-судьи.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from travel_agent.agent.schema import AgentOutput


def compare_entities(expected: dict[str, str], got: dict[str, str]) -> bool:
    """Все ожидаемые сущности совпали (лишние сущности в ответе допустимы)."""
    return all(got.get(key) == value for key, value in expected.items())


def evaluate_case(case: dict[str, Any], output: AgentOutput) -> dict[str, Any]:
    """Оценивает один кейс: исход + сущности."""
    expected_outcome = case["expected_outcome_type"]
    expected_entities = case.get("expected_entities") or {}
    got_entities = output.entities

    outcome_ok = output.outcome_type.value == expected_outcome
    entity_ok = compare_entities(expected_entities, got_entities)

    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "expected_outcome": expected_outcome,
        "got_outcome": output.outcome_type.value,
        "expected_entities": expected_entities,
        "got_entities": got_entities,
        "outcome_ok": outcome_ok,
        "entity_ok": entity_ok,
        "passed": outcome_ok and entity_ok,
    }


def _ratio(passed: int, total: int) -> float:
    return round(passed / total, 4) if total else 0.0


def _entity_accuracy(results: list[dict[str, Any]], key: str) -> dict[str, Any]:
    relevant = [r for r in results if key in r["expected_entities"]]
    matched = sum(1 for r in relevant if r["got_entities"].get(key) == r["expected_entities"][key])
    return {"matched": matched, "total": len(relevant), "accuracy": _ratio(matched, len(relevant))}


def compute_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Агрегирует метрики по всем кейсам."""
    total = len(results)

    outcome_ok = sum(1 for r in results if r["outcome_ok"])
    passed = sum(1 for r in results if r["passed"])

    entity_relevant = [r for r in results if r["expected_entities"]]
    entity_passed = sum(1 for r in entity_relevant if r["entity_ok"])

    escalation_cases = [r for r in results if r["expected_outcome"] == "escalation"]
    escalation_ok = sum(1 for r in escalation_cases if r["got_outcome"] == "escalation")

    by_category: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "total": 0})
    for result in results:
        by_category[result["category"]]["total"] += 1
        if result["passed"]:
            by_category[result["category"]]["passed"] += 1

    return {
        "total_cases": total,
        "task_success_rate": _ratio(passed, total),
        "outcome_accuracy": _ratio(outcome_ok, total),
        "entity_accuracy": _ratio(entity_passed, len(entity_relevant)),
        "flight_accuracy": _entity_accuracy(results, "flight_id"),
        "hotel_accuracy": _entity_accuracy(results, "hotel_id"),
        "tour_accuracy": _entity_accuracy(results, "tour_id"),
        "escalation_accuracy": _ratio(escalation_ok, len(escalation_cases)),
        "by_category": {
            category: {
                **counts,
                "accuracy": _ratio(counts["passed"], counts["total"]),
            }
            for category, counts in sorted(by_category.items())
        },
    }
