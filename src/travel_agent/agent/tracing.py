"""
Лёгкий трейсер для обсервабилити агента.

По образцу OpenTelemetry GenAI: дерево span'ов с видами `agent | llm | tool`,
длительностями и атрибутами (токены/стоимость для LLM, ошибки для tools).
В проде заменяется на OTel SDK + OTLP-экспортер с теми же атрибутами `gen_ai.*`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Span:
    """Один узел трейса."""

    name: str
    kind: str  # "agent" | "llm" | "tool"
    start_ts: float = 0.0
    end_ts: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)
    children: list["Span"] = field(default_factory=list)
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        return (self.end_ts - self.start_ts) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "duration_ms": round(self.duration_ms, 4),
            "attributes": self.attributes,
            "error": self.error,
            "children": [child.to_dict() for child in self.children],
        }


class Tracer:
    """Трейсер с поддержкой вложенных span'ов."""

    def __init__(self) -> None:
        self.root: Span | None = None
        self.stack: list[Span] = []

    def start_span(self, name: str, kind: str) -> Span:
        span = Span(name=name, kind=kind, start_ts=time.perf_counter())
        if self.stack:
            self.stack[-1].children.append(span)
        else:
            self.root = span
        self.stack.append(span)
        return span

    def end_span(
        self,
        attributes: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        span = self.stack.pop()
        span.end_ts = time.perf_counter()
        if attributes:
            span.attributes.update(attributes)
        if error:
            span.error = error

    def reset(self) -> None:
        self.root = None
        self.stack = []


def print_trace(span: Span, prefix: str = "", is_last: bool = True) -> None:
    """Печатает дерево трейса в стиле Langfuse / Phoenix."""
    connector = "└── " if is_last else "├── "
    extension = "    " if is_last else "│   "

    parts = [f"{span.duration_ms:7.2f}ms"]
    if span.kind == "llm":
        attrs = span.attributes
        parts.append(f"in={attrs.get('gen_ai.usage.input_tokens', 0)}")
        parts.append(f"out={attrs.get('gen_ai.usage.output_tokens', 0)}")
        parts.append(f"model={attrs.get('gen_ai.request.model', '?')}")
    elif span.kind == "tool":
        parts.append("ERR" if span.error else "ok")

    print(f"{prefix}{connector}{span.name:<34} [{' · '.join(parts)}]")
    for index, child in enumerate(span.children):
        print_trace(child, prefix + extension, index == len(span.children) - 1)


def trace_summary(span: Span) -> dict[str, Any]:
    """Сводка по дереву: токены, число LLM/tool-вызовов, ошибки, длительность."""
    total = {
        "input_tokens": 0,
        "output_tokens": 0,
        "llm_calls": 0,
        "tool_calls": 0,
        "tool_errors": 0,
        "duration_ms": 0.0,
    }

    def walk(node: Span) -> None:
        if node.kind == "llm":
            total["llm_calls"] += 1
            total["input_tokens"] += node.attributes.get("gen_ai.usage.input_tokens", 0)
            total["output_tokens"] += node.attributes.get("gen_ai.usage.output_tokens", 0)
        elif node.kind == "tool":
            total["tool_calls"] += 1
            if node.error:
                total["tool_errors"] += 1
        for child in node.children:
            walk(child)

    walk(span)
    total["duration_ms"] = round(span.duration_ms, 4)
    return total
