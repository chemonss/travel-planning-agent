#!/usr/bin/env python3
"""
Генерирует docs/EXAMPLES.md: реальные прогоны агента с трейсами на показательных
кейсах (рекомендация / info / уточнение / эскалация / многоходовый replanning через
память). Запуск: ../venv/bin/python scripts/make_examples.py
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from travel_agent.agent import run_agent  # noqa: E402
from travel_agent.agent.memory import MemoryStore  # noqa: E402
from travel_agent.agent.tracing import print_trace, trace_summary  # noqa: E402

OUT = _ROOT / "docs" / "EXAMPLES.md"


def _trace_text(root) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        print_trace(root)
    return buf.getvalue().rstrip()


def _block(title: str, request: str, group_id, output, root) -> str:
    summary = trace_summary(root)
    lines = [
        f"## {title}",
        "",
        f"**Запрос:** {request}" + (f"  (group_id={group_id})" if group_id else ""),
        "",
        "**Ответ агента:**",
        "",
        "```json",
        json.dumps(output.to_dict(), ensure_ascii=False, indent=2),
        "```",
        "",
        "**Трейс:**",
        "",
        "```",
        _trace_text(root),
        "",
        f"Summary: {json.dumps(summary, ensure_ascii=False)}",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    memory = MemoryStore(base_dir=Path(tempfile.mkdtemp(prefix="examples_mem_")))
    sections: list[str] = [
        "# Примеры работы агента",
        "",
        "Реальные прогоны LLM-driven агента (`qwen2.5:7b`) с трейсами обсервабилити. "
        "Каждый трейс показывает шаги рассуждения: вызовы инструментов, рефлексию и "
        "финальный structured-ответ. ID в рекомендациях валидируются по БД (галлюцинации "
        "перехватываются).",
        "",
    ]

    # 1. Рекомендация с реальными ID
    req = "Подбери поездку в Стамбул на 5 ночей для семьи с ребёнком, бюджет до 180000 рублей, без ночного прилёта."
    out, root = run_agent(req, "G-0001", session_id="ex-rec")
    sections.append(_block("Рекомендация (планирование с ограничениями)", req, "G-0001", out, root))

    # 2. Info по правилам сервиса (RAG)
    req = "Можно ли у вас бесплатно отменить отель после бронирования?"
    out, root = run_agent(req, None, session_id="ex-info")
    sections.append(_block("Справка по правилам (info + RAG)", req, None, out, root))

    # 3. Уточнение при нехватке данных
    req = "Хочу куда-нибудь съездить, посоветуйте."
    out, root = run_agent(req, None, session_id="ex-clar")
    sections.append(_block("Уточнение (недостаточно данных)", req, None, out, root))

    # 4. Эскалация по визовому риску
    req = "Оформите нам визы и страховку сами и подтвердите бронь без нашего участия."
    out, root = run_agent(req, "G-0001", session_id="ex-esc")
    sections.append(_block("Эскалация (визовый риск)", req, "G-0001", out, root))

    # 5. Многоходовый replanning через долгосрочную память
    sections.append("## Многоходовый диалог: переплан-ирование через память\n")
    sections.append(
        "Одна и та же сессия (`session=trip-demo`): на втором ходу агент опирается на "
        "сохранённый в памяти план первого хода (цифровой двойник группы).\n"
    )
    req1 = "Подбери поездку: перелёт и отель под бюджет группы."
    out1, root1 = run_agent(req1, "G-0001", session_id="trip-demo", memory=memory)
    sections.append(_block("Ход 1 — первичный подбор", req1, "G-0001", out1, root1))
    req2 = "Бюджет сократился на 20000 рублей, пересобери вариант подешевле."
    out2, root2 = run_agent(req2, "G-0001", session_id="trip-demo", memory=memory)
    sections.append(_block("Ход 2 — переплан после изменения бюджета", req2, "G-0001", out2, root2))

    OUT.write_text("\n".join(sections), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
