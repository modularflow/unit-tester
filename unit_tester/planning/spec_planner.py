from __future__ import annotations

import json
from typing import List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..config import AppConfig
from ..llm.client import LLMClient
from ..models import APISymbol, NLTestCase, NLTestSpec


PLANNER_SYSTEM = (
    "You are an expert software test architect. You design comprehensive, precise, and minimal-overlap "
    "behavioral test plans using first principles, boundary analysis, property-based thinking, and "
    "error-path exploration. You output only strict JSON that conforms to the requested schema."
)


def _build_planner_prompt(symbol: APISymbol) -> str:
    context = []
    context.append(f"Target symbol: {symbol.qualified_name} [{symbol.kind} in {symbol.language}]")
    if symbol.signature:
        context.append(f"Signature: {symbol.signature}")
    if symbol.docstring:
        context.append("Docstring/Comments:\n" + symbol.docstring)
    context_text = "\n".join(context)

    schema_hint = {
        "rationale": "Why these cases and how they ensure high coverage",
        "coverage_notes": [
            "Important boundaries, invariants, and properties to validate"
        ],
        "cases": [
            {
                "title": "Short, descriptive",
                "description": "Behavioral purpose of the test",
                "steps": ["Step-by-step interactions or setup"],
                "inputs": {"...": "Structured inputs where applicable"},
                "expected": {"...": "Observable outcomes or assertions"},
                "category": "functional|edge|boundary|error|property",
            }
        ],
    }
    schema_str = json.dumps(schema_hint, indent=2)

    prompt = f"""
{context_text}

Design a comprehensive set of natural-language test cases with:
- First-principles decomposition of behavior
- Edge and boundary conditions
- Error paths and invalid inputs
- Idempotence and invariants where applicable
- Minimal overlap, maximal coverage

Output strict JSON matching this schema (do not include any commentary or code):
{schema_str}
""".strip()
    return prompt


def plan_tests_for_symbols(
    symbols: List[APISymbol],
    config: AppConfig,
    progress_callback: Optional[Callable[[int, int, APISymbol], None]] = None,
    spec_callback: Optional[Callable[[int, int, NLTestSpec], None]] = None,
) -> List[NLTestSpec]:
    # Worker to plan a single symbol
    def do_plan(idx: int, sym: APISymbol) -> tuple[int, NLTestSpec]:
        client = LLMClient(config)
        prompt = _build_planner_prompt(sym)
        # Use temperature=1.0 for models that only accept default temperature
        raw = client.complete(prompt, system=PLANNER_SYSTEM, temperature=1.0, json_response=True)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                data = json.loads(raw[start : end + 1])
            else:
                # If the LLM didn't return usable JSON, signal an error so the caller can skip writing files
                raise RuntimeError("Planner LLM returned invalid JSON and no extractable object")
        spec = NLTestSpec(
            symbol=sym,
            rationale=data.get("rationale", ""),
            coverage_notes=data.get("coverage_notes", []),
            cases=[NLTestCase.model_validate(c) for c in data.get("cases", [])],
        )
        return idx, spec

    total = len(symbols)
    specs: List[NLTestSpec] = [None] * total  # type: ignore
    completed = 0

    with ThreadPoolExecutor(max_workers=max(1, config.planner_concurrency)) as executor:
        future_to_info = {executor.submit(do_plan, idx, sym): (idx, sym) for idx, sym in enumerate(symbols)}
        for future in as_completed(future_to_info):
            orig_idx, sym = future_to_info[future]
            try:
                idx, spec = future.result()
            except Exception:
                # Skip writing files when LLM fails; return a sentinel empty spec for progress only
                idx, spec = orig_idx, NLTestSpec(symbol=sym, rationale="", coverage_notes=[], cases=[])

            specs[idx] = spec
            completed += 1
            if spec_callback:
                try:
                    spec_callback(completed, total, spec)
                except Exception:
                    pass
            if progress_callback:
                try:
                    progress_callback(completed, total, sym)
                except Exception:
                    pass

    # Filter None (should not occur) and return in original order
    return [s for s in specs if s is not None]


