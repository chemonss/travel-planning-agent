#!/usr/bin/env python3
"""
Единый CLI-запуск агента планирования путешествий.

Примеры:
    # Одиночный запрос с группой
    python main.py -g G-0001 -r "Подбери поездку в Стамбул на 5 ночей, бюджет 180000"

    # Справочный (info) вопрос без группы
    python main.py -r "Можно ли бесплатно отменить отель?"

    # Показать трейс (обсервабилити)
    python main.py -g G-0002 -r "Нужен пляжный отдых в Дубае" --trace

    # Многоходовый диалог с общей памятью сессии
    python main.py -g G-0001 --session trip-123 --chat

    # E2E-оценка по qa.jsonl (пишет evaluation_report.md и data/eval/metrics.json)
    python main.py --eval
    python main.py --eval --limit 7   # gold-first прогон на первых кейсах
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _run_single(
    request: str, group_id: str | None, session_id: str | None, show_trace: bool
) -> None:
    from travel_agent.agent import run_agent
    from travel_agent.agent.tracing import print_trace, trace_summary

    output, root = run_agent(request, group_id, session_id=session_id)
    print(json.dumps(output.to_dict(), ensure_ascii=False, indent=2))

    if show_trace:
        print("\n=== Trace ===")
        print_trace(root)
        print("\nSummary:", json.dumps(trace_summary(root), ensure_ascii=False))


def _run_chat(group_id: str | None, session_id: str | None, show_trace: bool) -> None:
    """Интерактивный многоходовый режим с общей долгосрочной памятью сессии."""
    from travel_agent.agent import run_agent
    from travel_agent.agent.memory import MemoryStore
    from travel_agent.agent.tracing import print_trace, trace_summary

    memory = MemoryStore()
    session = session_id or group_id or "default"
    print(f"Диалоговый режим (session={session}). Пустая строка или 'exit' — выход.\n")

    while True:
        try:
            request = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not request or request.lower() in {"exit", "quit"}:
            break

        output, root = run_agent(request, group_id, session_id=session, memory=memory)
        print("Агент:", json.dumps(output.to_dict(), ensure_ascii=False, indent=2))
        if show_trace:
            print("\n=== Trace ===")
            print_trace(root)
            print("\nSummary:", json.dumps(trace_summary(root), ensure_ascii=False))
        print()


def _run_eval(qa_path: str | None, limit: int | None, save: bool) -> None:
    from travel_agent.evaluation.loaders import DEFAULT_QA_PATH
    from travel_agent.evaluation.run_qa_eval import print_metrics, run_evaluation, save_outputs

    report_data = run_evaluation(qa_path=qa_path or DEFAULT_QA_PATH, limit=limit)
    print_metrics(report_data)
    if save:
        save_outputs(report_data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Travel planning agent CLI")
    parser.add_argument("-r", "--request", help="Текст запроса пользователя")
    parser.add_argument("-g", "--group", default=None, help="Идентификатор группы, напр. G-0001")
    parser.add_argument("-s", "--session", default=None, help="ID сессии для долгосрочной памяти")
    parser.add_argument(
        "-m",
        "--model",
        default=None,
        choices=["qwen-7b", "qwen-3b", "gigachat", "gigachat-max"],
        help="Выбор модели (по умолчанию qwen-7b)",
    )
    parser.add_argument("--chat", action="store_true", help="Интерактивный многоходовый режим")
    parser.add_argument("--trace", action="store_true", help="Показать трейс выполнения")
    parser.add_argument("--eval", action="store_true", help="Запустить E2E-оценку по qa.jsonl")
    parser.add_argument("--qa", default=None, help="Путь к qa.jsonl (по умолчанию data/qa/qa.jsonl)")
    parser.add_argument("--limit", type=int, default=None, help="Ограничить число кейсов")
    parser.add_argument("--no-save", action="store_true", help="Не сохранять отчёт/метрики оценки")
    args = parser.parse_args()

    if args.model:
        from travel_agent.agent import llm_backend

        llm_backend.set_model(args.model)

    if args.eval:
        _run_eval(args.qa, args.limit, save=not args.no_save)
        return

    if args.chat:
        _run_chat(args.group, args.session, args.trace)
        return

    if not args.request:
        parser.error("укажите --request, --chat или --eval")

    _run_single(args.request, args.group, args.session, args.trace)


if __name__ == "__main__":
    main()
