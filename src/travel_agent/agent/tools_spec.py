"""
Спецификация инструментов для tool-calling агента.

Здесь:
- `TOOL_SCHEMAS` — OpenAI-совместимые JSON-описания инструментов, которые мы
  «рекламируем» модели (qwen сам формирует структурированные вызовы — Action ≥2);
- `execute_tool(name, args, context)` — диспетчер: исполняет реальный инструмент из
  слоя `tools/`, нормализует ошибки к `{ok: false, error: ...}` и обрезает выдачу,
  чтобы не раздувать контекст слабой модели;
- хелперы валидации существования ID в БД (защита от галлюцинаций).

Здесь НЕТ бизнес-логики выбора/маршрутизации — что и в каком порядке вызывать,
решает модель в `agent_loop`.
"""

from __future__ import annotations

from typing import Any

from travel_agent.tools.budget import build_budget_summary
from travel_agent.tools.db import TravelDatabase
from travel_agent.tools.flights import search_flights
from travel_agent.tools.groups import get_full_group_profile
from travel_agent.tools.hotels import get_hotel_by_id, search_hotels
from travel_agent.tools.tours import get_tour_by_id, search_tours
from travel_agent.rag.retriever import retrieve_policy_context

# Сколько кандидатов максимум возвращаем модели (экономия контекста).
_MAX_CANDIDATES = 6

OUTCOME_TYPES = ["info", "recommendation", "clarification", "escalation", "rejection"]

# Имя терминального инструмента: его вызов завершает цикл.
SUBMIT_TOOL = "submit_answer"


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_group_profile",
            "description": (
                "Вернуть профиль группы: маршрут, даты, число ночей, бюджет, состав "
                "(возраст, гражданство, заметки) и предпочтения. Вызови это первым, "
                "чтобы узнать origin_city, destination, nights, budget_rub."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "group_id": {"type": "string", "description": "Например, G-0001"}
                },
                "required": ["group_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": (
                "Найти перелёты по жёстким ограничениям. Возвращает реальные flight_id "
                "с ценами. Меняй ограничения, если результат не подходит."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin_city": {"type": "string"},
                    "destination": {"type": "string", "description": "Код, напр. IST"},
                    "max_price_rub": {"type": "integer"},
                    "baggage_required": {"type": "boolean"},
                    "direct_only": {"type": "boolean"},
                    "avoid_early_departure": {"type": "boolean", "description": "Исключить вылет до 07:00"},
                    "avoid_night_arrival": {"type": "boolean", "description": "Исключить прилёт после 23:00"},
                },
                "required": ["origin_city", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_hotels",
            "description": (
                "Найти отели по жёстким ограничениям. Возвращает реальные hotel_id с "
                "ценой за ночь и итоговой ценой за nights ночей."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "nights": {"type": "integer"},
                    "max_total_price_rub": {"type": "integer"},
                    "breakfast_required": {"type": "boolean"},
                    "free_cancellation_required": {"type": "boolean"},
                    "min_stars": {"type": "integer"},
                },
                "required": ["destination", "nights"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tours",
            "description": "Найти пакетные туры (перелёт+отель). Возвращает реальные tour_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "max_total_price_rub": {"type": "integer"},
                    "require_transfer": {"type": "boolean"},
                },
                "required": ["destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_budget",
            "description": (
                "Посчитать итог и проверить бюджет. Сложи цены выбранных позиций и "
                "сравни с budget_rub. Возвращает total, budget_ok, gap."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_rub": {"type": "integer"},
                    "flight_price_rub": {"type": "integer"},
                    "hotel_total_price_rub": {"type": "integer"},
                    "tour_total_price_rub": {"type": "integer"},
                },
                "required": ["budget_rub"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_policy",
            "description": (
                "Найти правила сервиса (багаж, тарифы, ночной прилёт, отмена, подбор "
                "туров, визы) в policy-документах. Используй для info-вопросов и чтобы "
                "понять, какие ограничения применять."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": (
                "Вспомнить, что уже известно по этой сессии/группе из долгосрочной "
                "памяти (предыдущие планы, уточнения, изменения бюджета)."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "Сохранить важный факт/решение в долгосрочную память сессии, чтобы "
                "вернуться к нему на следующих шагах диалога."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Что запомнить"}
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": SUBMIT_TOOL,
            "description": (
                "Выдать финальный структурированный ответ. flight_id/hotel_id/tour_id "
                "заполняй ТОЛЬКО реальными значениями из результатов поиска. Если "
                "данных не хватает или требования конфликтуют — используй "
                "clarification/escalation/rejection без выдуманных ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "outcome_type": {"type": "string", "enum": OUTCOME_TYPES},
                    "answer": {"type": "string", "description": "Текст ответа пользователю"},
                    "flight_id": {"type": "string"},
                    "hotel_id": {"type": "string"},
                    "tour_id": {"type": "string"},
                    "estimated_total_price": {"type": "integer"},
                    "decision_rationale": {"type": "string"},
                    "warnings": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["outcome_type", "answer"],
            },
        },
    },
]


def _trim(rows: list[dict[str, Any]], fields: list[str]) -> list[dict[str, Any]]:
    return [{key: row.get(key) for key in fields} for row in rows[:_MAX_CANDIDATES]]


def _tool_get_group_profile(args: dict[str, Any], db: TravelDatabase) -> dict[str, Any]:
    profile = get_full_group_profile(args["group_id"], db)
    return {
        "summary": profile["summary"],
        "group_comment": profile["group"].get("group_comment"),
        "members": _trim(profile["members"], ["traveler_id", "age", "citizenship", "notes"]),
        "preferences": _trim(
            profile["preferences"], ["traveler_id", "preference_type", "preference_value", "comment"]
        ),
    }


def _tool_search_flights(args: dict[str, Any], db: TravelDatabase) -> dict[str, Any]:
    rows = search_flights(
        origin_city=args.get("origin_city"),
        destination=args.get("destination"),
        max_price_rub=args.get("max_price_rub"),
        baggage_required=args.get("baggage_required"),
        direct_only=bool(args.get("direct_only", False)),
        avoid_early_departure=bool(args.get("avoid_early_departure", False)),
        avoid_night_arrival=bool(args.get("avoid_night_arrival", False)),
        db=db,
    )
    return {
        "count": len(rows),
        "flights": _trim(
            rows,
            ["flight_id", "price_rub", "baggage_included", "stops", "departure_time", "arrival_time", "fare_type"],
        ),
    }


def _tool_search_hotels(args: dict[str, Any], db: TravelDatabase) -> dict[str, Any]:
    rows = search_hotels(
        destination=args.get("destination"),
        nights=args.get("nights"),
        max_total_price_rub=args.get("max_total_price_rub"),
        breakfast_required=args.get("breakfast_required"),
        free_cancellation_required=args.get("free_cancellation_required"),
        min_stars=args.get("min_stars"),
        db=db,
    )
    return {
        "count": len(rows),
        "hotels": _trim(
            rows,
            ["hotel_id", "stars", "price_per_night_rub", "total_price_rub", "breakfast_included", "free_cancellation", "rating"],
        ),
    }


def _tool_search_tours(args: dict[str, Any], db: TravelDatabase) -> dict[str, Any]:
    rows = search_tours(
        destination=args.get("destination"),
        max_total_price_rub=args.get("max_total_price_rub"),
        require_flight=True,
        require_transfer=bool(args.get("require_transfer", False)),
        db=db,
    )
    return {
        "count": len(rows),
        "tours": _trim(
            rows,
            ["tour_id", "total_price_rub", "includes_flight", "includes_transfer", "hotel_id"],
        ),
    }


def _tool_calculate_budget(args: dict[str, Any], db: TravelDatabase) -> dict[str, Any]:
    total = (
        int(args.get("flight_price_rub") or 0)
        + int(args.get("hotel_total_price_rub") or 0)
        + int(args.get("tour_total_price_rub") or 0)
    )
    summary = build_budget_summary(total, args.get("budget_rub"))
    return summary


def _tool_retrieve_policy(args: dict[str, Any], db: TravelDatabase) -> dict[str, Any]:
    result = retrieve_policy_context(query=args["query"], top_k=int(args.get("top_k") or 3))
    return {"context": result["context"]}


# Имя инструмента -> функция исполнения. submit_answer обрабатывается циклом отдельно.
_DISPATCH = {
    "get_group_profile": _tool_get_group_profile,
    "search_flights": _tool_search_flights,
    "search_hotels": _tool_search_hotels,
    "search_tours": _tool_search_tours,
    "calculate_budget": _tool_calculate_budget,
    "retrieve_policy": _tool_retrieve_policy,
}


def execute_tool(name: str, args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Исполняет инструмент по имени, нормализуя ошибки к {ok: false, error}.

    @param name Имя инструмента из tool_call модели.
    @param args Аргументы, сформированные моделью.
    @param context Среда исполнения: `db`, `session_id`, `memory`.
    @return JSON-сериализуемый результат для возврата модели.
    """
    db: TravelDatabase = context["db"]

    try:
        if name in _DISPATCH:
            return {"ok": True, **_DISPATCH[name](args, db)}

        if name == "recall_memory":
            memory = context["memory"]
            return {"ok": True, "memory": memory.recall(context["session_id"])}

        if name == "save_memory":
            memory = context["memory"]
            memory.append(context["session_id"], args.get("content", ""))
            return {"ok": True, "saved": True}

        return {"ok": False, "error": f"Unknown tool: {name}"}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def flight_exists(flight_id: str, db: TravelDatabase) -> bool:
    return db.fetch_one("SELECT flight_id FROM flights WHERE flight_id = ?", (flight_id,)) is not None


def validate_entities(
    flight_id: str | None,
    hotel_id: str | None,
    tour_id: str | None,
    db: TravelDatabase,
) -> list[str]:
    """Возвращает список несуществующих ID (для защиты от галлюцинаций)."""
    invalid: list[str] = []
    if flight_id and not flight_exists(flight_id, db):
        invalid.append(f"flight_id={flight_id}")
    if hotel_id and get_hotel_by_id(hotel_id, db) is None:
        invalid.append(f"hotel_id={hotel_id}")
    if tour_id and get_tour_by_id(tour_id, db) is None:
        invalid.append(f"tour_id={tour_id}")
    return invalid
