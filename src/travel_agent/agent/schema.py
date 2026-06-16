"""
Структурированный контракт ответа агента.

`AgentOutput` — единый формат, который возвращает агент и который без парсинга
свободного текста читает слой оценки (метрики по `outcome_type` и сущностям).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class OutcomeType(str, Enum):
    """Тип исхода обращения, совместимый с `expected_outcome_type` из qa.jsonl."""

    INFO = "info"
    RECOMMENDATION = "recommendation"
    CLARIFICATION = "clarification"
    ESCALATION = "escalation"
    REJECTION = "rejection"


class RequestCategory(str, Enum):
    """Категория запроса, совместимая с полем `category` из qa.jsonl."""

    INFO = "info"
    PLANNING = "planning"
    REPLANNING = "replanning"
    PREFERENCE_CONFLICT = "preference_conflict"
    BUDGET_LIMIT = "budget_limit"
    CLARIFICATION = "clarification"
    ESCALATION = "escalation"
    EDGE_CASE = "edge_case"


# Сопоставление исхода и статуса из reference-схемы README (approved/clarification/
# escalation/rejected).
_OUTCOME_TO_STATUS: dict[OutcomeType, str] = {
    OutcomeType.INFO: "approved",
    OutcomeType.RECOMMENDATION: "approved",
    OutcomeType.CLARIFICATION: "clarification",
    OutcomeType.ESCALATION: "escalation",
    OutcomeType.REJECTION: "rejected",
}


class AgentOutput(BaseModel):
    """Структурированный ответ агента.

    Поля `flight_id`/`hotel_id`/`tour_id` заполняются только реальными ID из БД.
    Свободный текст для пользователя — в `answer`; обоснование выбора — в
    `decision_rationale`.
    """

    outcome_type: OutcomeType
    answer: str = ""
    flight_id: str | None = None
    hotel_id: str | None = None
    tour_id: str | None = None
    estimated_total_price: int | None = None
    decision_rationale: str = ""
    warnings: list[str] = Field(default_factory=list)
    group_id: str | None = None
    destination: str | None = None
    category: RequestCategory | None = None

    @property
    def status(self) -> str:
        """Статус из reference-схемы README."""
        return _OUTCOME_TO_STATUS[self.outcome_type]

    @property
    def entities(self) -> dict[str, str]:
        """Непустые сущности ответа для сравнения с `expected_entities`."""
        result: dict[str, str] = {}
        if self.flight_id:
            result["flight_id"] = self.flight_id
        if self.hotel_id:
            result["hotel_id"] = self.hotel_id
        if self.tour_id:
            result["tour_id"] = self.tour_id
        return result

    def to_dict(self) -> dict[str, Any]:
        """Сериализует ответ в обычный dict со строковыми enum-значениями."""
        data = self.model_dump(mode="json")
        data["status"] = self.status
        return data
