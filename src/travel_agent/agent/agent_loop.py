"""
Агентный цикл (tool-calling ReAct) — ядро принятия решений.

Модель (qwen) сама выбирает инструменты, получает результаты и **меняет план** по
ходу (Reasoning). Когда модель вызывает `submit_answer`, выполняется:
1) валидация существования ID в БД (защита от галлюцинаций);
2) рефлексия — само-оценка результата относительно запроса; при проблемах ответ
   возвращается в цикл на доработку (Reflection).

Здесь нет if-then бизнес-логики выбора перелётов/отелей/исхода — всё решает модель.
"""

from __future__ import annotations

import json
from typing import Any

from travel_agent.agent import llm_backend
from travel_agent.agent.schema import AgentOutput, OutcomeType
from travel_agent.agent.tools_spec import (
    SUBMIT_TOOL,
    TOOL_SCHEMAS,
    execute_tool,
    validate_entities,
)
from travel_agent.agent.tracing import Tracer
from travel_agent.tools.db import TravelDatabase

MAX_ITERATIONS = 12
MAX_REFLECTIONS = 1

_FINALIZE_HINT = (
    "Похоже, данных уже достаточно. На следующем шаге вызови submit_answer с лучшим "
    "найденным вариантом (только реальные ID из результатов поиска) либо верни "
    "clarification/escalation/rejection, если вариант невозможен."
)

_SEARCH_HINT = (
    "Не сдавайся раньше времени. Сначала собери реальные варианты: при необходимости "
    "вызови get_group_profile, затем search_flights и search_hotels (или search_tours), "
    "проверь бюджет через calculate_budget — и только потом submit_answer."
)

_REFLECTION_SYSTEM = (
    "Ты — строгий, но справедливый ревьюер ответа агента путешествий. Отклоняй ответ "
    "(ok=false) ТОЛЬКО при явной ошибке: (1) тип recommendation, но из текста/цены видно "
    "превышение бюджета («превышает бюджет», цена > бюджета) — recommendation так нельзя, "
    "нужен rejection или clarification; (2) проигнорировано жёсткое требование (завтрак / "
    "бесплатная отмена / прямой рейс), хотя подходящий вариант был доступен; (3) затронут "
    "визовый/документный риск, но тип не escalation; (4) очевидно неуместный outcome_type. "
    "В остальных случаях ok=true — не придирайся к формулировкам. Верни СТРОГО JSON: "
    '{"ok": true|false, "issue": "коротко"}.'
)


def _llm_step(tracer: Tracer, messages: list[dict[str, Any]]) -> dict[str, Any]:
    tracer.start_span("llm.step", kind="llm")
    response = llm_backend.chat_with_tools(messages, TOOL_SCHEMAS, max_tokens=600)
    usage = response["usage"]
    tracer.end_span(
        attributes={
            "gen_ai.request.model": llm_backend.model_name(),
            "gen_ai.usage.input_tokens": usage["input_tokens"],
            "gen_ai.usage.output_tokens": usage["output_tokens"],
            "tool_calls": len(response["tool_calls"]),
        }
    )
    return response


def _reflect(tracer: Tracer, user_request: str, answer_payload: dict[str, Any]) -> dict[str, Any]:
    """Само-оценка предложенного ответа. Возвращает {ok, issue}."""
    tracer.start_span("llm.reflection", kind="llm")
    messages = [
        {"role": "system", "content": _REFLECTION_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Запрос пользователя: {user_request}\n"
                f"Предложенный ответ: {json.dumps(answer_payload, ensure_ascii=False)}"
            ),
        },
    ]
    response = llm_backend.chat(messages, max_tokens=150)
    usage = response["usage"]
    tracer.end_span(
        attributes={
            "gen_ai.request.model": llm_backend.model_name(),
            "gen_ai.usage.input_tokens": usage["input_tokens"],
            "gen_ai.usage.output_tokens": usage["output_tokens"],
        }
    )
    content = response["content"] or ""
    try:
        start = content.index("{")
        end = content.rindex("}") + 1
        verdict = json.loads(content[start:end])
        return {"ok": bool(verdict.get("ok", True)), "issue": str(verdict.get("issue", ""))}
    except (ValueError, KeyError, json.JSONDecodeError):
        # Не удалось разобрать вердикт — не блокируем выдачу.
        return {"ok": True, "issue": ""}


def _finalize(
    args: dict[str, Any],
    *,
    request: str,
    group_id: str | None,
    session_id: str,
    db: TravelDatabase,
    memory: Any,
    stats: dict[str, Any],
) -> AgentOutput:
    """Строит AgentOutput, отбрасывает невалидные ID и сохраняет план в память."""
    invalid = validate_entities(args.get("flight_id"), args.get("hotel_id"), args.get("tour_id"), db)
    if invalid:
        # Защита от галлюцинаций: убираем несуществующие ID и понижаем до clarification.
        stats["invalid_id_events"] += 1
        args = dict(args)
        args["flight_id"] = args["hotel_id"] = args["tour_id"] = None
        if args.get("outcome_type") == "recommendation":
            args["outcome_type"] = "clarification"
            args["answer"] = (
                "Не удалось надёжно подобрать вариант: подходящие позиции не подтвердились "
                "в базе. Уточните, пожалуйста, требования (даты, бюджет, направление)."
            )
    output = _build_output(args, group_id)
    memory.save_plan(
        session_id,
        {
            "request": request,
            "outcome_type": output.outcome_type.value,
            "flight_id": output.flight_id,
            "hotel_id": output.hotel_id,
            "tour_id": output.tour_id,
            "estimated_total_price": output.estimated_total_price,
        },
    )
    return output


def _build_output(args: dict[str, Any], group_id: str | None) -> AgentOutput:
    try:
        outcome = OutcomeType(args.get("outcome_type"))
    except ValueError:
        outcome = OutcomeType.CLARIFICATION
    return AgentOutput(
        outcome_type=outcome,
        answer=str(args.get("answer", "")),
        flight_id=args.get("flight_id") or None,
        hotel_id=args.get("hotel_id") or None,
        tour_id=args.get("tour_id") or None,
        estimated_total_price=args.get("estimated_total_price"),
        decision_rationale=str(args.get("decision_rationale", "")),
        warnings=list(args.get("warnings") or []),
        group_id=group_id,
    )


def run_loop(
    user_request: str,
    system_prompt: str,
    *,
    group_id: str | None,
    session_id: str,
    db: TravelDatabase,
    memory: Any,
    tracer: Tracer,
    max_iterations: int = MAX_ITERATIONS,
) -> tuple[AgentOutput, dict[str, Any]]:
    """Прогоняет агентный цикл и возвращает (AgentOutput, статистику ходов)."""
    context = {"db": db, "session_id": session_id, "memory": memory}

    user_content = user_request
    if group_id:
        user_content = f"[group_id={group_id}] {user_request}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    stats = {"iterations": 0, "replans": 0, "reflections": 0, "invalid_id_events": 0, "nudges": 0}
    reflections_used = 0
    finalize_hinted = False
    searched = False

    def finalize(args: dict[str, Any]) -> AgentOutput:
        return _finalize(
            args,
            request=user_request,
            group_id=group_id,
            session_id=session_id,
            db=db,
            memory=memory,
            stats=stats,
        )

    for _ in range(max_iterations):
        stats["iterations"] += 1
        response = _llm_step(tracer, messages)
        messages.append(response["assistant_message"])
        tool_calls = response["tool_calls"]

        if not tool_calls:
            # Модель ответила текстом без вызова submit_answer.
            stats["nudges"] += 1
            # Если для группы ещё не искали варианты — подтолкнём собрать их (анти-сдача).
            if group_id and not searched and stats["nudges"] <= 2:
                messages.append({"role": "user", "content": _SEARCH_HINT})
                continue
            # На первом ходу (ещё не собрала данные) — мягкий хинт; иначе финализируем.
            if stats["iterations"] == 1:
                messages.append({"role": "user", "content": _FINALIZE_HINT})
                continue
            return _force_submit(tracer, messages, finalize), stats

        submitted: AgentOutput | None = None
        for call in tool_calls:
            name = call["name"]
            args = call["arguments"]

            if name == SUBMIT_TOOL:
                invalid = validate_entities(
                    args.get("flight_id"), args.get("hotel_id"), args.get("tour_id"), db
                )
                if invalid:
                    stats["invalid_id_events"] += 1
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(
                                {
                                    "ok": False,
                                    "error": "Эти ID не найдены в БД: "
                                    + ", ".join(invalid)
                                    + ". Используй только реальные ID из результатов поиска "
                                    "или верни clarification/escalation/rejection без ID.",
                                },
                                ensure_ascii=False,
                            ),
                        }
                    )
                    break

                verdict = {"ok": True, "issue": ""}
                if reflections_used < MAX_REFLECTIONS:
                    stats["reflections"] += 1
                    reflections_used += 1
                    verdict = _reflect(tracer, user_request, args)

                if not verdict["ok"]:
                    stats["replans"] += 1
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(
                                {"ok": False, "error": f"Рефлексия выявила проблему: {verdict['issue']}. Доработай ответ."},
                                ensure_ascii=False,
                            ),
                        }
                    )
                    break

                submitted = finalize(args)
                break

            # Обычный инструмент: исполняем и возвращаем результат модели.
            if name.startswith("search_"):
                searched = True
            tracer.start_span(f"tool.{name}", kind="tool")
            result = execute_tool(name, args, context)
            tracer.end_span(
                attributes={"tool.name": name},
                error=None if result.get("ok", True) else result.get("error"),
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

        if submitted is not None:
            return submitted, stats

        # Ближе к лимиту итераций — один раз настойчиво просим завершить.
        if not finalize_hinted and stats["iterations"] >= max_iterations - 3:
            finalize_hinted = True
            messages.append({"role": "user", "content": _FINALIZE_HINT})

    # Лимит итераций исчерпан — форсируем структурированный submit_answer.
    return _force_submit(tracer, messages, finalize), stats


def _force_submit(tracer: Tracer, messages: list[dict[str, Any]], finalize: Any) -> AgentOutput:
    """Принудительно получает submit_answer от модели (tool_choice) и финализирует."""
    messages.append(
        {
            "role": "user",
            "content": "Оформи итог через submit_answer. ОБЯЗАТЕЛЬНО укажи outcome_type "
            "(info — вопрос о правилах; recommendation — есть вариант с реальными ID; "
            "clarification — не хватает данных; escalation — нужен оператор; rejection — "
            "невыполнимо) и понятный answer.",
        }
    )
    submit_only = [t for t in TOOL_SCHEMAS if t["function"]["name"] == SUBMIT_TOOL]
    tracer.start_span("llm.force_submit", kind="llm")
    result_args: dict[str, Any] | None = None
    try:
        response = llm_backend.chat_with_tools(
            messages,
            submit_only,
            max_tokens=400,
            tool_choice={"type": "function", "function": {"name": SUBMIT_TOOL}},
        )
        usage = response["usage"]
        tracer.end_span(
            attributes={
                "gen_ai.usage.input_tokens": usage["input_tokens"],
                "gen_ai.usage.output_tokens": usage["output_tokens"],
            }
        )
        for call in response["tool_calls"]:
            if call["name"] == SUBMIT_TOOL:
                args = dict(call["arguments"])
                has_ids = any(args.get(k) for k in ("flight_id", "hotel_id", "tour_id"))
                if not args.get("outcome_type"):
                    # Модель не указала тип — выводим из наличия найденных ID.
                    args["outcome_type"] = "recommendation" if has_ids else "clarification"
                if not args.get("answer"):
                    args["answer"] = "См. структурированный результат подбора."
                result_args = args
                break

        if result_args is None:
            # Tool_call не получен — пробуем разобрать JSON из текстового ответа модели.
            content = response.get("content") or ""
            if "{" in content and "}" in content:
                try:
                    parsed = json.loads(content[content.index("{") : content.rindex("}") + 1])
                    if parsed.get("outcome_type") or parsed.get("answer"):
                        result_args = parsed
                except (ValueError, json.JSONDecodeError):
                    pass
    except Exception as exc:
        tracer.end_span(error=str(exc))

    if result_args is None:
        # Берём последний осмысленный текст модели, чтобы не терять её ответ.
        # Пропускаем «мусор»: сырые tool_call-строки, которые модель иногда пишет текстом.
        last_text = ""
        for msg in reversed(messages):
            if msg.get("role") != "assistant" or not msg.get("content"):
                continue
            candidate = str(msg["content"]).strip()
            if any(marker in candidate for marker in ("</tool_call>", '"arguments"', '"name":')):
                continue
            last_text = candidate
            break
        result_args = {
            "outcome_type": "clarification",
            "answer": last_text
            or "Уточните, пожалуйста, ключевые требования (направление, даты, состав, бюджет).",
        }
    return finalize(result_args)
