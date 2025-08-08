from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class BDDStep(BaseModel):
    keyword: str  # Given | When | Then | And | But
    text: str
    data_table: Optional[List[List[str]]] = None
    doc_string: Optional[str] = None


class BDDScenario(BaseModel):
    name: str
    tags: List[str] = Field(default_factory=list)
    steps: List[BDDStep] = Field(default_factory=list)
    examples: Optional[List[dict]] = None  # for Scenario Outline
    is_outline: bool = False


class BDDFeature(BaseModel):
    name: str
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    background: List[BDDStep] = Field(default_factory=list)
    scenarios: List[BDDScenario] = Field(default_factory=list)


class NLBDDFeatureSpec(BaseModel):
    rationale: str = ""
    features: List[BDDFeature] = Field(default_factory=list)


class BDDCapability(BaseModel):
    name: str
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    involved_symbols: List[str] = Field(
        default_factory=list
    )  # language-prefixed qualified names, e.g., "rust:module.Type.method"
    critical_paths: List[List[str]] = Field(default_factory=list)  # high-level step outlines


class BDDSurvey(BaseModel):
    rationale: str = ""
    capabilities: List[BDDCapability] = Field(default_factory=list)


