from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Callable

from ..config import AppConfig
from .models import NLBDDFeatureSpec, BDDFeature, BDDScenario, BDDStep


def _to_gherkin(feature: BDDFeature) -> str:
    lines: List[str] = []
    if feature.tags:
        lines.append(" ".join(feature.tags))
    lines.append(f"Feature: {feature.name}")
    if feature.description:
        lines.append("  " + feature.description)
    if feature.background:
        lines.append("  Background:")
        for step in feature.background:
            lines.append(f"    {step.keyword} {step.text}")
    for scenario in feature.scenarios:
        if scenario.tags:
            lines.append("  " + " ".join(scenario.tags))
        prefix = "Scenario Outline" if scenario.is_outline else "Scenario"
        lines.append(f"  {prefix}: {scenario.name}")
        for step in scenario.steps:
            lines.append(f"    {step.keyword} {step.text}")
        if scenario.is_outline and scenario.examples:
            # Simple examples table (keys from first row)
            headers = sorted({k for row in scenario.examples for k in row.keys()})
            lines.append("    Examples:")
            lines.append("      | " + " | ".join(headers) + " |")
            for row in scenario.examples:
                lines.append("      | " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
    return "\n".join(lines) + "\n"


def write_features(
    spec: NLBDDFeatureSpec,
    out_dir: Path,
    progress_callback: Optional[Callable[[int, int, BDDFeature], None]] = None,
) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    total = len(spec.features)
    for idx, feat in enumerate(spec.features, start=1):
        content = _to_gherkin(feat)
        file_path = out_dir / (feat.name.lower().replace(" ", "_") + ".feature")
        file_path.write_text(content, encoding="utf-8")
        written.append(file_path)
        if progress_callback:
            try:
                progress_callback(idx, total, feat)
            except Exception:
                pass
    return written


