from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table
from dotenv import load_dotenv

from .config import AppConfig
from .models import NLTestSpec, RenderedTest, TargetSpec
from .bdd.models import NLBDDFeatureSpec
from .bdd.planner import plan_bdd_features, plan_bdd_survey
from .bdd.renderer import write_features
from .parsing.discovery import discover_public_api
from .planning.spec_planner import plan_tests_for_symbols
from .rendering.test_renderer import render_tests


app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


def _load_config(model: Optional[str]) -> AppConfig:
    load_dotenv(override=False)
    config = AppConfig()
    if model:
        config.openai_model = model
    return config


@app.command()
def plan(
    path: str = typer.Argument(..., help="Path to the library root to analyze"),
    out_dir: str = typer.Option(".unit_tester/specs", help="Directory to write NL specs"),
    include_langs: List[str] = typer.Option(
        ["python", "javascript", "typescript", "go", "java", "rust"],
        help="Languages to include for API discovery",
    ),
    model: Optional[str] = typer.Option(None, help="OpenAI model to use for planning"),
    skip_existing: bool = typer.Option(True, help="Skip planning if a spec file already exists"),
):
    """Analyze a codebase and produce natural-language behavioral test specs (JSON)."""
    cfg = _load_config(model)
    root = Path(path).resolve()
    if not root.exists():
        raise typer.BadParameter(f"Path not found: {root}")

    console.print(f"[bold]Discovering public API in[/bold] {root}")
    symbols = discover_public_api(root, include_langs=include_langs, ignore_globs=cfg.ignore_globs)
    console.print(f"Found [bold]{len(symbols)}[/bold] symbols to plan tests for")

    # Progress callback for planning
    def _plan_progress(i, total, sym):
        pct = int(i * 100 / max(1, total))
        console.print(f"[dim]Planning:[/dim] {i}/{total} ({pct}%) - {sym.qualified_name}")

    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    def _spec_ready(i, total, spec: NLTestSpec):
        # Only write when we have non-empty cases or a non-empty rationale
        if not spec.cases and not (spec.rationale or spec.coverage_notes):
            pct = int(i * 100 / max(1, total))
            console.print(
                f"[yellow]Skipping write[/yellow] empty spec for {spec.symbol.qualified_name}  [dim]{i}/{total} ({pct}%)\n"
            )
            return
        spec_file = out_path / f"{spec.symbol.language}__{spec.symbol.safe_id}.json"
        spec_file.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
        pct = int(i * 100 / max(1, total))
        console.print(f"[green]Wrote[/green] {spec_file}  [dim]{i}/{total} ({pct}%)\n")

    # Optionally skip symbols that already have a spec file
    if skip_existing:
        filtered_symbols: List = []
        for s in symbols:
            candidate = out_path / f"{s.language}__{s.safe_id}.json"
            if candidate.exists() and candidate.stat().st_size > 0:
                console.print(f"[yellow]Skipping existing spec[/yellow] {candidate}")
                continue
            filtered_symbols.append(s)
        symbols = filtered_symbols

    specs = plan_tests_for_symbols(symbols, cfg, progress_callback=_plan_progress, spec_callback=_spec_ready)

    # Already wrote each file as soon as it's planned via _spec_ready

    console.print(f"Wrote [bold]{len([s for s in specs if s.cases or s.rationale or s.coverage_notes])}[/bold] spec files to {out_path}")


@app.command()
def render(
    specs_dir: str = typer.Argument(".unit_tester/specs", help="Directory with NL specs JSON"),
    target: str = typer.Option(
        "auto",
        help="Target as <language>:<framework> or 'auto' to infer per language (python→pytest, js/ts→jest, go→testing, java→junit5, rust→cargo)",
    ),
    out_dir: str = typer.Option(".unit_tester/tests", help="Directory to write generated tests"),
    model: Optional[str] = typer.Option(None, help="OpenAI model to use for rendering"),
    skip_existing: bool = typer.Option(True, help="Skip rendering if a test file already exists"),
):
    """Render executable unit tests from NL specs using the specified target."""
    cfg = _load_config(model)
    specs_path = Path(specs_dir).resolve()
    if not specs_path.exists():
        raise typer.BadParameter(f"Specs directory not found: {specs_path}")

    spec_files = list(specs_path.glob("*.json"))
    if not spec_files:
        console.print("[yellow]No spec files found[/yellow]")
        raise typer.Exit(code=0)

    specs: List[NLTestSpec] = []
    for file in spec_files:
        data = json.loads(file.read_text(encoding="utf-8"))
        specs.append(NLTestSpec.model_validate(data))

    # Progress callback for rendering
    def _render_progress(i, total, spec):
        pct = int(i * 100 / max(1, total))
        console.print(f"[dim]Rendering:[/dim] {i}/{total} ({pct}%) - {spec.symbol.qualified_name}")

    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    def _test_ready(i, total, test: RenderedTest):
        if not test.content.strip():
            pct = int(i * 100 / max(1, total))
            console.print(
                f"[yellow]Skipping write[/yellow] empty test for {test.spec.symbol.qualified_name}  [dim]{i}/{total} ({pct}%)\n"
            )
            return
        file_path = out_path / test.file_name
        file_path.write_text(test.content, encoding="utf-8")
        pct = int(i * 100 / max(1, total))
        console.print(f"[green]Created[/green] {file_path}  [dim]{i}/{total} ({pct}%)\n")

    # If a fixed target is provided, use it for all specs
    if target != "auto":
        target_spec = TargetSpec.from_string(target)
        # Skip already rendered tests if requested
        if skip_existing:
            filtered_specs: List[NLTestSpec] = []
            for s in specs:
                dummy = RenderedTest(spec=s, target=target_spec, content="")
                candidate = out_path / dummy.file_name
                if candidate.exists() and candidate.stat().st_size > 0:
                    console.print(f"[yellow]Skipping existing[/yellow] {candidate}")
                    continue
                filtered_specs.append(s)
            specs = filtered_specs

        console.print(f"[bold]Target[/bold] {target_spec.language}:{target_spec.framework} for {len(specs)} specs")
        tests = render_tests(specs, target_spec, cfg, progress_callback=_render_progress, test_callback=_test_ready)
        all_tests = tests
    else:
        # Auto mode: map by language
        lang_to_target = {
            "python": "python:pytest",
            "javascript": "javascript:jest",
            "typescript": "typescript:jest",
            "go": "go:testing",
            "java": "java:junit5",
            "rust": "rust:cargo",
        }

        # Group specs by language
        grouped: dict[str, List[NLTestSpec]] = {}
        for s in specs:
            grouped.setdefault(s.symbol.language, []).append(s)

        all_tests: List[RenderedTest] = []
        for lang, items in grouped.items():
            mapped = lang_to_target.get(lang)
            if not mapped:
                console.print(f"[yellow]No default target for language[/yellow] {lang}; skipping")
                continue
            target_spec = TargetSpec.from_string(mapped)

            # Skip existing per language group
            to_render: List[NLTestSpec] = []
            if skip_existing:
                for s in items:
                    dummy = RenderedTest(spec=s, target=target_spec, content="")
                    candidate = out_path / dummy.file_name
                    if candidate.exists() and candidate.stat().st_size > 0:
                        console.print(f"[yellow]Skipping existing[/yellow] {candidate}")
                        continue
                    to_render.append(s)
            else:
                to_render = items

            if not to_render:
                continue

            console.print(f"[bold]Target[/bold] {target_spec.language}:{target_spec.framework} for {len(to_render)} specs")
            tests = render_tests(to_render, target_spec, cfg, progress_callback=_render_progress, test_callback=_test_ready)
            all_tests.extend(tests)

    # Files are already written incrementally via _test_ready; show a summary table
    table = Table(title="Generated Tests")
    table.add_column("Symbol")
    table.add_column("File")
    for t in all_tests:
        table.add_row(t.spec.symbol.qualified_name, t.file_name)
    console.print(table)


@app.command()
def run(
    target: str = typer.Option("python:pytest", help="Target as <language>:<framework>"),
    tests_dir: str = typer.Option(".unit_tester/tests", help="Directory with generated tests"),
):
    """Attempt to run generated tests for certain targets (best-effort)."""
    target_spec = TargetSpec.from_string(target)
    if target_spec.language == "python" and target_spec.framework == "pytest":
        import subprocess

        console.print(f"[bold]Running pytest in[/bold] {tests_dir}")
        completed = subprocess.run(["pytest", tests_dir, "-q"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        console.print(completed.stdout)
        raise typer.Exit(code=completed.returncode)
    else:
        console.print("[yellow]Run is not implemented for this target yet. Please run with your language's test runner.[/yellow]")


@app.command(name="bdd-plan")
def bdd_plan(
    path: str = typer.Argument(..., help="Path to the library root to analyze"),
    out_dir: str = typer.Option(".unit_tester/bdd", help="Directory to write BDD specs (feature JSON)"),
    include_langs: List[str] = typer.Option(
        ["python", "javascript", "typescript", "go", "java", "rust"],
        help="Languages to include for API discovery",
    ),
    model: Optional[str] = typer.Option(None, help="OpenAI model to use for BDD planning"),
    skip_existing: bool = typer.Option(True, help="Skip if BDD JSON already exists and is non-empty"),
):
    """Analyze a codebase and produce high-level BDD feature specs (JSON)."""
    cfg = _load_config(model)
    root = Path(path).resolve()
    if not root.exists():
        raise typer.BadParameter(f"Path not found: {root}")

    console.print(f"[bold]Discovering public API in[/bold] {root}")
    symbols = discover_public_api(root, include_langs=include_langs, ignore_globs=cfg.ignore_globs)
    console.print(f"Found [bold]{len(symbols)}[/bold] symbols to plan BDD for")

    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    json_path = out_path / "features.json"

    if skip_existing and json_path.exists() and json_path.stat().st_size > 0:
        console.print(f"[yellow]Skipping existing BDD plan[/yellow] {json_path}")
        return

    # Step 1: Survey (write incrementally)
    survey = plan_bdd_survey(symbols, cfg)
    survey_path = out_path / "survey.json"
    survey_path.write_text(survey.model_dump_json(indent=2), encoding="utf-8")
    console.print(f"[green]Wrote[/green] {survey_path}")

    # Step 2-3: Per-capability features and merge
    spec = plan_bdd_features(symbols, cfg)
    json_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    console.print(f"[green]Wrote[/green] {json_path}")


@app.command(name="bdd-render")
def bdd_render(
    bdd_json: str = typer.Argument(".unit_tester/bdd/features.json", help="BDD features JSON"),
    out_dir: str = typer.Option(".unit_tester/bdd/features", help="Directory to write .feature files"),
    skip_existing: bool = typer.Option(True, help="Skip writing .feature if file already exists"),
):
    """Render BDD features into Gherkin .feature files."""
    path = Path(bdd_json).resolve()
    if not path.exists():
        raise typer.BadParameter(f"BDD JSON not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    spec = NLBDDFeatureSpec.model_validate(data)

    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    def _feat_progress(i, total, feat):
        pct = int(i * 100 / max(1, total))
        file_path = out_path / (feat.name.lower().replace(" ", "_") + ".feature")
        if skip_existing and file_path.exists() and file_path.stat().st_size > 0:
            console.print(f"[yellow]Skipping existing feature[/yellow] {file_path}")
            return
        # Write as we go
        from .bdd.renderer import _to_gherkin  # local import to avoid cycle in typing
        content = _to_gherkin(feat)
        file_path.write_text(content, encoding="utf-8")
        console.print(f"[green]Wrote[/green] {file_path}  [dim]{i}/{total} ({pct}%)")

    # Stream write via progress callback
    write_features(spec, out_path, progress_callback=_feat_progress)
    console.print(f"Wrote features to {out_path}")

if __name__ == "__main__":  # pragma: no cover
    app()


