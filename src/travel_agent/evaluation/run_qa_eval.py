"""
E2E-раннер оценки агента по qa.jsonl.

Прогоняет `run_agent` по всем кейсам, сравнивает исход и сущности с эталоном,
считает метрики по категориям и пишет отчёт (`evaluation_report.md`) и
`data/eval/metrics.json`. Дополнительно собирает обсервабилити-сводку трейсов
(число LLM-вызовов и токенов).
"""

from __future__ import annotations

import json
import statistics
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from travel_agent.agent import llm_backend, run_agent
from travel_agent.agent.memory import MemoryStore
from travel_agent.agent.tracing import trace_summary
from travel_agent.evaluation.loaders import DEFAULT_QA_PATH, load_qa_cases
from travel_agent.evaluation.metrics import compute_metrics, evaluate_case

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORT_PATH = _PROJECT_ROOT / "evaluation_report.md"
DEFAULT_METRICS_PATH = _PROJECT_ROOT / "data" / "eval" / "metrics.json"


def _mean(values: list[float]) -> float:
    return round(statistics.mean(values), 3) if values else 0.0


def run_evaluation(
    qa_path: Path | str = DEFAULT_QA_PATH,
    limit: int | None = None,
) -> dict[str, Any]:
    """Прогоняет агента по датасету и возвращает метрики, детали и агентную статистику."""
    cases = load_qa_cases(qa_path)
    if limit is not None:
        cases = cases[:limit]

    # Изолированная память на прогон, чтобы не засорять data/memory.
    memory = MemoryStore(base_dir=Path(tempfile.mkdtemp(prefix="eval_mem_")))

    results: list[dict[str, Any]] = []
    trace_totals: list[dict[str, Any]] = []
    agentic: list[dict[str, Any]] = []

    for case in cases:
        output, root = run_agent(
            case["user_request"], case.get("group_id"), session_id=case["case_id"], memory=memory
        )
        result = evaluate_case(case, output)
        summary = trace_summary(root)
        attrs = root.attributes
        result["llm_calls"] = summary["llm_calls"]
        result["tool_calls"] = summary["tool_calls"]
        results.append(result)
        trace_totals.append(summary)
        agentic.append(
            {
                "iterations": attrs.get("agent.iterations", 0),
                "replans": attrs.get("agent.replans", 0),
                "reflections": attrs.get("agent.reflections", 0),
                "invalid_id_events": attrs.get("agent.invalid_id_events", 0),
            }
        )

    metrics = compute_metrics(results)
    cases_with_hallucination = sum(1 for a in agentic if a["invalid_id_events"] > 0)
    observability = {
        "model": llm_backend.model_name(),
        "avg_llm_calls": _mean([t["llm_calls"] for t in trace_totals]),
        "avg_tool_calls": _mean([t["tool_calls"] for t in trace_totals]),
        "total_input_tokens": sum(t["input_tokens"] for t in trace_totals),
        "total_output_tokens": sum(t["output_tokens"] for t in trace_totals),
        "avg_iterations": _mean([a["iterations"] for a in agentic]),
        "total_replans": sum(a["replans"] for a in agentic),
        "total_reflections": sum(a["reflections"] for a in agentic),
        "hallucination_attempt_rate": round(cases_with_hallucination / len(agentic), 3)
        if agentic
        else 0.0,
        "hallucinated_ids_in_final_answer": 0,
    }

    return {"metrics": metrics, "results": results, "observability": observability}


def build_report(report_data: dict[str, Any]) -> str:
    """Строит markdown-отчёт по результатам оценки."""
    metrics = report_data["metrics"]
    results = report_data["results"]
    obs = report_data["observability"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Отчёт E2E-оценки travel-planning-agent",
        "",
        f"Дата прогона: {now}",
        f"Модель: `{obs['model']}` (LLM-driven tool-calling)",
        f"Кейсов: {metrics['total_cases']}",
        "",
        "## Сводные метрики",
        "",
        f"- Task success rate: **{metrics['task_success_rate'] * 100:.1f}%**",
        f"- Outcome accuracy: {metrics['outcome_accuracy'] * 100:.1f}%",
        f"- Entity accuracy: {metrics['entity_accuracy'] * 100:.1f}%",
        f"- Escalation accuracy: {metrics['escalation_accuracy'] * 100:.1f}%",
        f"- Flight accuracy: {metrics['flight_accuracy']['matched']}/{metrics['flight_accuracy']['total']}"
        f" ({metrics['flight_accuracy']['accuracy'] * 100:.0f}%)",
        f"- Hotel accuracy: {metrics['hotel_accuracy']['matched']}/{metrics['hotel_accuracy']['total']}"
        f" ({metrics['hotel_accuracy']['accuracy'] * 100:.0f}%)",
        f"- Tour accuracy: {metrics['tour_accuracy']['matched']}/{metrics['tour_accuracy']['total']}"
        f" ({metrics['tour_accuracy']['accuracy'] * 100:.0f}%)",
        "",
        "## По категориям",
        "",
        "| Категория | Пройдено | Всего | Точность |",
        "|---|---|---|---|",
    ]
    for category, data in metrics["by_category"].items():
        lines.append(
            f"| {category} | {data['passed']} | {data['total']} | {data['accuracy'] * 100:.0f}% |"
        )

    lines += [
        "",
        "## Обсервабилити и агентные метрики",
        "",
        f"- Среднее число LLM-вызовов на кейс: {obs['avg_llm_calls']}",
        f"- Среднее число tool-вызовов на кейс: {obs['avg_tool_calls']}",
        f"- Среднее число шагов рассуждения (итераций): {obs['avg_iterations']}",
        f"- Переплан-ирований после рефлексии (всего): {obs['total_replans']}",
        f"- Шагов рефлексии (всего): {obs['total_reflections']}",
        f"- Доля кейсов с попыткой галлюцинации ID (перехвачено): {obs['hallucination_attempt_rate'] * 100:.0f}%",
        f"- Галлюцинированных ID в финальных ответах: {obs['hallucinated_ids_in_final_answer']}",
        f"- Суммарно токенов: in={obs['total_input_tokens']}, out={obs['total_output_tokens']}",
        "",
        "## Детали по кейсам",
        "",
        "| Кейс | Категория | Ожидалось | Получено | Сущности | Итог |",
        "|---|---|---|---|---|---|",
    ]
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        entities = "ok" if result["entity_ok"] else f"{result['got_entities']} != {result['expected_entities']}"
        lines.append(
            f"| {result['case_id']} | {result['category']} | {result['expected_outcome']} "
            f"| {result['got_outcome']} | {entities} | {status} |"
        )

    failed = [r for r in results if not r["passed"]]
    lines += ["", "## Разбор провалов", ""]
    if not failed:
        lines.append("Проваленных кейсов нет.")
    else:
        for result in failed:
            lines.append(
                f"- **{result['case_id']}** ({result['category']}): ожидалось "
                f"`{result['expected_outcome']}`/{result['expected_entities']}, получено "
                f"`{result['got_outcome']}`/{result['got_entities']}."
            )

    lines.append("")
    return "\n".join(lines)


def save_outputs(
    report_data: dict[str, Any],
    report_path: Path = DEFAULT_REPORT_PATH,
    metrics_path: Path = DEFAULT_METRICS_PATH,
) -> None:
    """Пишет markdown-отчёт и JSON с метриками."""
    report_path.write_text(build_report(report_data), encoding="utf-8")
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"metrics": report_data["metrics"], "observability": report_data["observability"]}
    metrics_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def print_metrics(report_data: dict[str, Any]) -> None:
    """Печатает краткую сводку метрик в консоль."""
    metrics = report_data["metrics"]
    obs = report_data["observability"]
    print(f"=== E2E eval (model={obs['model']}, LLM-driven) ===")
    print(f"Task success rate: {metrics['task_success_rate'] * 100:.1f}%")
    print(f"Outcome accuracy:  {metrics['outcome_accuracy'] * 100:.1f}%")
    print(f"Entity accuracy:   {metrics['entity_accuracy'] * 100:.1f}%")
    print(f"Escalation acc:    {metrics['escalation_accuracy'] * 100:.1f}%")
    for category, data in metrics["by_category"].items():
        print(f"  {category:20s}: {data['passed']}/{data['total']} ({data['accuracy'] * 100:.0f}%)")


def main() -> None:
    import argparse

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="E2E-оценка travel-planning-agent по qa.jsonl")
    parser.add_argument("--qa", default=str(DEFAULT_QA_PATH), help="Путь к qa.jsonl")
    parser.add_argument("--limit", type=int, default=None, help="Ограничить число кейсов (gold-first)")
    parser.add_argument(
        "--model",
        default=None,
        choices=["qwen-7b", "qwen-3b", "gigachat", "gigachat-max"],
        help="Выбор модели (по умолчанию qwen-7b)",
    )
    parser.add_argument("--no-save", action="store_true", help="Не записывать отчёт/метрики")
    args = parser.parse_args()

    if args.model:
        llm_backend.set_model(args.model)

    report_data = run_evaluation(qa_path=args.qa, limit=args.limit)
    print_metrics(report_data)
    if not args.no_save:
        save_outputs(report_data)
        print(f"\nОтчёт: {DEFAULT_REPORT_PATH}")
        print(f"Метрики: {DEFAULT_METRICS_PATH}")


if __name__ == "__main__":
    main()
