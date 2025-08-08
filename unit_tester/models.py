from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class APISymbol(BaseModel):
    name: str
    qualified_name: str
    kind: str  # function | class | method
    language: str
    file_path: str
    signature: Optional[str] = None
    docstring: Optional[str] = None

    @property
    def safe_id(self) -> str:
        return (
            f"{self.qualified_name.replace('.', '__').replace(':', '__').replace(' ', '_')}"
        )


class NLTestCase(BaseModel):
    title: str
    description: str
    steps: List[str] = Field(default_factory=list)
    inputs: dict = Field(default_factory=dict)
    expected: dict = Field(default_factory=dict)
    category: str = Field(default="functional")  # functional | edge | boundary | error | property


class NLTestSpec(BaseModel):
    symbol: APISymbol
    rationale: str
    coverage_notes: List[str] = Field(default_factory=list)
    cases: List[NLTestCase] = Field(default_factory=list)


class TargetSpec(BaseModel):
    language: str
    framework: str

    @staticmethod
    def from_string(target: str) -> "TargetSpec":
        parts = target.split(":", 1)
        if len(parts) != 2:
            raise ValueError("Target must be <language>:<framework>")
        return TargetSpec(language=parts[0].strip().lower(), framework=parts[1].strip().lower())


class RenderedTest(BaseModel):
    spec: NLTestSpec
    target: TargetSpec
    content: str

    @property
    def file_name(self) -> str:
        lang = self.target.language
        framework = self.target.framework
        base = f"test_{self.spec.symbol.safe_id}"
        if lang == "python" and framework == "pytest":
            return f"{base}.py"
        if lang in {"javascript", "typescript"} and framework == "jest":
            ext = "ts" if lang == "typescript" else "js"
            return f"{base}.test.{ext}"
        if lang == "go" and framework == "testing":
            return f"{base}_test.go"
        if lang == "java" and framework.startswith("junit"):
            return f"{base}.java"
        if lang == "rust" and framework == "cargo":
            return f"{base}.rs"
        return f"{base}.txt"


