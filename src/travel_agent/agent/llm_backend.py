"""
LLM-бэкенд агента с выбором модели (провайдера).

Поддерживаемые модели (ключ `--model` / env `LLM_MODEL`):
- `qwen-7b`      — локальный qwen2.5:7b через Ollama (по умолчанию);
- `qwen-3b`      — локальный qwen2.5:3b через Ollama (быстрее, слабее);
- `gigachat`     — облачный GigaChat-2 (нужен `GIGACHAT_TOKEN`);
- `gigachat-max` — облачный GigaChat-2-Max (нужен `GIGACHAT_TOKEN`).

Главная функция — `chat_with_tools` (tool-calling), плюс `chat` (текст, для рефлексии).
Интерфейс одинаков для всех провайдеров: возвращается dict с `content`, `tool_calls`
(список {id, name, arguments, arguments_raw}), `assistant_message` (для истории) и `usage`.
"""

from __future__ import annotations

import json
import os
import uuid
from functools import lru_cache
from typing import Any

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"

# Ключ модели -> (провайдер, имя модели у провайдера).
MODELS: dict[str, tuple[str, str]] = {
    "qwen-7b": ("ollama", "qwen2.5:7b"),
    "qwen-3b": ("ollama", "qwen2.5:3b"),
    "gigachat": ("gigachat", "GigaChat-2"),
    "gigachat-max": ("gigachat", "GigaChat-2-Max"),
}

_active_model: str | None = None


def set_model(key: str) -> None:
    """Выбрать активную модель по ключу из `MODELS`."""
    global _active_model
    if key not in MODELS:
        raise ValueError(f"Неизвестная модель: {key}. Доступно: {', '.join(MODELS)}")
    _active_model = key


def active_model_key() -> str:
    if _active_model:
        return _active_model
    env_key = os.getenv("LLM_MODEL")
    if env_key in MODELS:
        return env_key
    # Обратная совместимость: QWEN_MODEL=qwen2.5:3b → qwen-3b.
    if os.getenv("QWEN_MODEL") == "qwen2.5:3b":
        return "qwen-3b"
    return "qwen-7b"


def _provider_model() -> tuple[str, str]:
    return MODELS[active_model_key()]


def model_name() -> str:
    """Человекочитаемое имя активной модели (для отчётов/трейсов)."""
    return _provider_model()[1]


def base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)


# ── Ollama (OpenAI-совместимый API) ──────────────────────────────────────


def _ollama_client():
    from openai import OpenAI

    return OpenAI(base_url=base_url(), api_key="ollama", timeout=180.0, max_retries=0)


def _usage_openai(completion: Any) -> dict[str, int]:
    usage = getattr(completion, "usage", None)
    return {
        "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
    }


def _parse_arguments(raw: Any) -> tuple[dict[str, Any], str]:
    if isinstance(raw, dict):
        return raw, json.dumps(raw, ensure_ascii=False)
    if not raw:
        return {}, "{}"
    try:
        return json.loads(raw), raw
    except (json.JSONDecodeError, TypeError):
        return {}, str(raw)


def _ollama_chat_with_tools(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    tool_choice: Any,
    model: str,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice
    completion = _ollama_client().chat.completions.create(**kwargs)
    message = completion.choices[0].message
    raw_tool_calls = getattr(message, "tool_calls", None) or []

    tool_calls = []
    assistant_tool_calls = []
    for call in raw_tool_calls:
        args, args_raw = _parse_arguments(call.function.arguments)
        tool_calls.append(
            {"id": call.id, "name": call.function.name, "arguments": args, "arguments_raw": args_raw}
        )
        assistant_tool_calls.append(
            {"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": args_raw}}
        )

    assistant_message: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if assistant_tool_calls:
        assistant_message["tool_calls"] = assistant_tool_calls

    return {
        "content": message.content,
        "tool_calls": tool_calls,
        "assistant_message": assistant_message,
        "usage": _usage_openai(completion),
    }


def _ollama_chat(messages: list[dict[str, Any]], max_tokens: int, temperature: float, model: str) -> dict[str, Any]:
    completion = _ollama_client().chat.completions.create(
        model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
    )
    return {"content": completion.choices[0].message.content or "", "usage": _usage_openai(completion)}


# ── GigaChat (через langchain_gigachat) ──────────────────────────────────


@lru_cache(maxsize=4)
def _gigachat_client(model: str, max_tokens: int):
    from langchain_gigachat.chat_models import GigaChat

    token = os.getenv("GIGACHAT_TOKEN") or os.getenv("GIGACHAT_CREDENTIALS")
    if not token:
        raise RuntimeError(
            "Не задан GIGACHAT_TOKEN — укажите authorization key из личного кабинета Sber в .env"
        )
    return GigaChat(
        credentials=token,
        model=model,
        scope=os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
        verify_ssl_certs=False,
        profanity_check=False,
        max_tokens=max_tokens,
        timeout=180,
    )


def _to_langchain(messages: list[dict[str, Any]]) -> list[Any]:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

    out: list[Any] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        if role == "system":
            out.append(SystemMessage(content=content))
        elif role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            tcs = []
            for tc in m.get("tool_calls") or []:
                fn = tc["function"]
                try:
                    args = json.loads(fn["arguments"])
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tcs.append({"name": fn["name"], "args": args, "id": tc["id"], "type": "tool_call"})
            out.append(AIMessage(content=content, tool_calls=tcs))
        elif role == "tool":
            out.append(ToolMessage(content=content, tool_call_id=m.get("tool_call_id") or "t"))
    return out


def _from_langchain(resp: Any) -> dict[str, Any]:
    tool_calls = []
    assistant_tool_calls = []
    for tc in getattr(resp, "tool_calls", None) or []:
        cid = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
        args = tc.get("args") or {}
        args_raw = json.dumps(args, ensure_ascii=False)
        tool_calls.append({"id": cid, "name": tc.get("name"), "arguments": args, "arguments_raw": args_raw})
        assistant_tool_calls.append(
            {"id": cid, "type": "function", "function": {"name": tc.get("name"), "arguments": args_raw}}
        )

    content = resp.content if isinstance(getattr(resp, "content", None), str) else ""
    assistant_message: dict[str, Any] = {"role": "assistant", "content": content or ""}
    if assistant_tool_calls:
        assistant_message["tool_calls"] = assistant_tool_calls

    usage = getattr(resp, "usage_metadata", None) or {}
    return {
        "content": content or None,
        "tool_calls": tool_calls,
        "assistant_message": assistant_message,
        "usage": {
            "input_tokens": usage.get("input_tokens", 0) or 0,
            "output_tokens": usage.get("output_tokens", 0) or 0,
        },
    }


def _normalize_tool_choice(tool_choice: Any) -> Any:
    if isinstance(tool_choice, dict):
        return tool_choice.get("function", {}).get("name", "auto")
    return tool_choice


def _gigachat_chat_with_tools(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    max_tokens: int,
    tool_choice: Any,
    model: str,
) -> dict[str, Any]:
    client = _gigachat_client(model, max_tokens)
    bound = client.bind_tools(tools, tool_choice=_normalize_tool_choice(tool_choice)) if tools else client
    resp = bound.invoke(_to_langchain(messages))
    return _from_langchain(resp)


def _gigachat_chat(messages: list[dict[str, Any]], max_tokens: int, model: str) -> dict[str, Any]:
    client = _gigachat_client(model, max_tokens)
    resp = client.invoke(_to_langchain(messages))
    usage = getattr(resp, "usage_metadata", None) or {}
    content = resp.content if isinstance(getattr(resp, "content", None), str) else ""
    return {
        "content": content or "",
        "usage": {
            "input_tokens": usage.get("input_tokens", 0) or 0,
            "output_tokens": usage.get("output_tokens", 0) or 0,
        },
    }


# ── Публичный интерфейс ──────────────────────────────────────────────────


def chat_with_tools(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    max_tokens: int = 512,
    temperature: float = 0.0,
    tool_choice: Any = None,
) -> dict[str, Any]:
    """Один ход модели с доступом к инструментам (дispatch по провайдеру).

    @param tool_choice Опционально форсировать вызов инструмента, например
        {"type": "function", "function": {"name": "submit_answer"}}.
    """
    provider, model = _provider_model()
    if provider == "gigachat":
        return _gigachat_chat_with_tools(messages, tools, max_tokens, tool_choice, model)
    return _ollama_chat_with_tools(messages, tools, max_tokens, temperature, tool_choice, model)


def chat(messages: list[dict[str, Any]], max_tokens: int = 256, temperature: float = 0.0) -> dict[str, Any]:
    """Простой текстовый вызов модели (без инструментов)."""
    provider, model = _provider_model()
    if provider == "gigachat":
        return _gigachat_chat(messages, max_tokens, model)
    return _ollama_chat(messages, max_tokens, temperature, model)
