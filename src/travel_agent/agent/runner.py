"""
Оркестратор агента: единая точка входа `run_agent`.

Собирает адаптивную роль (базовый system_prompt + контекст из долгосрочной памяти
сессии — Role адаптируется по ходу взаимодействия), запускает tool-calling цикл и
возвращает структурированный `AgentOutput` плюс корневой span трейса.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from travel_agent.agent import agent_loop
from travel_agent.agent.memory import MemoryStore
from travel_agent.agent.schema import AgentOutput
from travel_agent.agent.tracing import Span, Tracer
from travel_agent.tools.db import TravelDatabase

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SYSTEM_PROMPT_PATH = _PROJECT_ROOT / "prompts" / "system_prompt.md"


@lru_cache(maxsize=1)
def _base_system_prompt() -> str:
    try:
        return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return "Ты — агент планирования путешествий."


def _memory_context_block(memory_state: dict[str, Any]) -> str:
    """Формирует блок «память сессии» для адаптивной роли."""
    notes = memory_state.get("notes", [])
    plans = memory_state.get("plans", [])
    if not notes and not plans:
        return ""

    lines = ["\n\n## Контекст из памяти этой сессии (учитывай его)"]
    for note in notes[-5:]:
        lines.append(f"- заметка: {note.get('content')}")
    for plan in plans[-3:]:
        lines.append(
            f"- прошлое решение: {plan.get('outcome_type')} "
            f"(flight={plan.get('flight_id')}, hotel={plan.get('hotel_id')}, tour={plan.get('tour_id')})"
        )
    return "\n".join(lines)


def run_agent(
    user_request: str,
    group_id: str | None = None,
    session_id: str | None = None,
    db: TravelDatabase | None = None,
    memory: MemoryStore | None = None,
) -> tuple[AgentOutput, Span]:
    """Запускает агента на одном обращении.

    @param user_request Текст запроса пользователя.
    @param group_id Идентификатор группы (если применимо).
    @param session_id Идентификатор сессии для долгосрочной памяти
        (по умолчанию = group_id или "default").
    @param db Опциональная обёртка БД.
    @param memory Опциональное хранилище памяти.
    @return Кортеж (AgentOutput, корневой span трейса).
    """
    db = db or TravelDatabase()
    memory = memory or MemoryStore()
    session = session_id or group_id or "default"

    # Адаптивная роль: базовый промпт дополняется контекстом из памяти сессии.
    memory_state = memory.recall(session)
    system_prompt = _base_system_prompt() + _memory_context_block(memory_state)

    tracer = Tracer()
    tracer.start_span("agent.run", kind="agent")

    try:
        output, stats = agent_loop.run_loop(
            user_request,
            system_prompt,
            group_id=group_id,
            session_id=session,
            db=db,
            memory=memory,
            tracer=tracer,
        )
        tracer.end_span(
            attributes={
                "agent.outcome_type": output.outcome_type.value,
                "agent.group_id": group_id,
                "agent.session_id": session,
                "agent.iterations": stats["iterations"],
                "agent.replans": stats["replans"],
                "agent.reflections": stats["reflections"],
                "agent.invalid_id_events": stats["invalid_id_events"],
            }
        )
    except Exception as exc:
        tracer.end_span(error=str(exc))
        raise

    return output, tracer.root
