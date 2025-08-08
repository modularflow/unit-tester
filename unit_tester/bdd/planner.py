from __future__ import annotations

import json
from typing import List, Optional

from ..config import AppConfig
from ..llm.client import LLMClient
from ..models import APISymbol
from .models import NLBDDFeatureSpec, BDDFeature, BDDScenario, BDDStep, BDDSurvey, BDDCapability


BDD_PLANNER_SYSTEM = (
    "You are a senior QA engineer designing high-level BDD features. Identify cross-module, cross-class flows, "
    "user journeys, and system behaviors. Use first principles to cover happy paths, edge cases, error paths, and "
    "security/permissions where relevant. Output only strict JSON in the requested schema."
)


def _build_bdd_survey_prompt(symbols: List[APISymbol]) -> str:
    outline = []
    outline.append("Context: The following public API surface exists (summarized):")
    for s in symbols[:100]:  # cap context for prompt size
        sig = f" | sig: {s.signature}" if s.signature else ""
        outline.append(f"- {s.language}:{s.qualified_name} [{s.kind}]{sig}")
    outline_text = "\n".join(outline)

    survey_schema = {
        "rationale": "Holistic coverage rationale",
        "capabilities": [
            {
                "name": "High-level capability",
                "description": "Business-relevant capability the system provides",
                "tags": ["@core", "@security"],
                "involved_symbols": ["rust:module.Type.method"],
                "critical_paths": [["user action", "system response"]],
            }
        ],
    }

    return f"""
{outline_text}

Survey the codebase and enumerate 6-12 high-level capabilities/end-to-end flows. Identify involved symbols and critical paths.

Output strict JSON with this schema (no commentary):
{json.dumps(survey_schema, indent=2)}
""".strip()


def plan_bdd_survey(symbols: List[APISymbol], config: AppConfig) -> BDDSurvey:
    client = LLMClient(config)
    prompt = _build_bdd_survey_prompt(symbols)
    raw = client.complete(prompt, system=BDD_PLANNER_SYSTEM, json_response=True)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            data = json.loads(raw[start : end + 1])
        else:
            data = {"rationale": "LLM returned non-JSON", "capabilities": []}

    return BDDSurvey.model_validate(data)


def _build_bdd_feature_prompt(capability: BDDCapability) -> str:
    schema_hint = {
        "rationale": "Why these features and coverage",
        "features": [
            {
                "name": "Feature Name",
                "description": "Short description",
                "tags": ["@api", "@auth"],
                "background": [{"keyword": "Given", "text": "some setup"}],
                "scenarios": [
                    {
                        "name": "Scenario name",
                        "tags": ["@happy"],
                        "steps": [
                            {"keyword": "Given", "text": "precondition"},
                            {"keyword": "When", "text": "action"},
                            {"keyword": "Then", "text": "expected outcome"},
                        ],
                        "is_outline": False,
                        "examples": None,
                    }
                ],
            }
        ],
    }
    cap = capability.model_dump()
    return (
        "You are refining a single capability into concrete BDD features."
        "\nCapability JSON:\n" + json.dumps(cap, indent=2) +
        "\nOutput strict JSON with this schema (no commentary):\n" + json.dumps(schema_hint, indent=2)
    )


def plan_bdd_features(symbols: List[APISymbol], config: AppConfig) -> NLBDDFeatureSpec:
    # 3-step: survey -> per-capability feature plans -> merge
    survey = plan_bdd_survey(symbols, config)
    client = LLMClient(config)
    all_features: List[BDDFeature] = []
    for cap in survey.capabilities:
        prompt = _build_bdd_feature_prompt(cap)
        raw = client.complete(prompt, system=BDD_PLANNER_SYSTEM, json_response=True)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                data = json.loads(raw[start : end + 1])
            else:
                data = {"features": []}
        spec = NLBDDFeatureSpec.model_validate(data)
        all_features.extend(spec.features)

    return NLBDDFeatureSpec(rationale=survey.rationale, features=all_features)


