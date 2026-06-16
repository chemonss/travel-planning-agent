#!/usr/bin/env python3
"""Диагностика отдельных кейсов: что делает агент по шагам и что отвечает."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from travel_agent.agent import run_agent  # noqa: E402
from travel_agent.agent.memory import MemoryStore  # noqa: E402


def _steps(span, acc):
    for ch in span.children:
        if ch.kind == "tool":
            acc.append(ch.name.replace("tool.", ""))
        elif ch.kind == "llm" and ch.name == "llm.reflection":
            acc.append("[reflect]")
        _steps(ch, acc)
    return acc


def main():
    wanted = set(sys.argv[1:]) or {"Q-001"}
    cases = {json.loads(l)["case_id"]: json.loads(l) for l in open(_ROOT / "data/qa/qa.jsonl")}
    mem = MemoryStore(base_dir=Path(tempfile.mkdtemp()))
    for cid in sys.argv[1:]:
        c = cases[cid]
        out, root = run_agent(c["user_request"], c.get("group_id"), session_id=cid, memory=mem)
        steps = _steps(root, [])
        print(f"\n=== {cid} [{c['category']}] g={c.get('group_id')} ===")
        print("req:", c["user_request"])
        print("expect:", c["expected_outcome_type"], c.get("expected_entities"))
        print("got:   ", out.outcome_type.value,
              {k: v for k, v in {"flight_id": out.flight_id, "hotel_id": out.hotel_id, "tour_id": out.tour_id}.items() if v},
              f"price={out.estimated_total_price}")
        print("steps:", " -> ".join(steps))
        print("answer:", (out.answer or "")[:280])


if __name__ == "__main__":
    main()
