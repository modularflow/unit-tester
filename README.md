# unit-tester

Language-agnostic unit test generation framework powered by LLMs. It discovers your public API, plans natural-language test specs, renders executable tests for popular frameworks, and can run them (for certain targets).

## Features

- Discover public API across multiple languages (Python, JavaScript/TypeScript, Go, Java, Rust)
- Plan high-quality, natural-language test specs with rationales and coverage notes
- Render executable tests for common frameworks (pytest, Jest, Go testing, JUnit 5, Cargo)
- Generate BDD feature specs and Gherkin `.feature` files
- Skip-existing, incremental workflows with progress output

## Requirements

- Python >= 3.10
- An OpenAI API key

## Installation

```bash
pip install unit-tester
# or, for isolation
pipx install unit-tester
```

## Quickstart

```bash
# 1) Set your API key (or use a .env file; see Configuration below)
export OPENAI_API_KEY=sk-...

# 2) Plan natural-language specs for a codebase
unit-tester plan .

# 3) Render executable tests (auto-selects target per language)
unit-tester render --target auto

# 4) Optionally run tests (currently implemented for Python/pytest)
unit-tester run --target python:pytest
```

This will create:

```
.unit_tester/
  specs/   # Natural-language spec JSON files
  tests/   # Rendered executable test files
  bdd/
    survey.json
    features.json
    features/*.feature
```

## CLI

The CLI is implemented with Typer. Use `--help` on any command for details.

### plan
Analyze a codebase and produce natural-language behavioral test specs (JSON).

```bash
unit-tester plan PATH [--out-dir .unit_tester/specs] \
  [--include-langs python javascript typescript go java rust] \
  [--model <openai-model>] \
  [--skip-existing / --no-skip-existing]
```

- PATH: path to the library root to analyze
- --out-dir: directory to write NL spec files
- --include-langs: languages to include for API discovery
- --model: override model used for planning
- --skip-existing: skip writing a spec if a non-empty file already exists (default)

Specs are written incrementally as they are planned to `<out-dir>/*.json` and include
rationales, coverage notes, and test cases.

### render
Render executable unit tests from NL specs using a specified target or `auto` mapping.

```bash
unit-tester render [SPECS_DIR] [--target auto|<language:framework>] \
  [--out-dir .unit_tester/tests] \
  [--model <openai-model>] \
  [--skip-existing / --no-skip-existing]
```

- SPECS_DIR: directory with NL spec JSON files (default `.unit_tester/specs`)
- --target:
  - auto: infer per-language framework mapping
  - or explicitly specify `<language>:<framework>` (e.g., `python:pytest`)
- --out-dir: directory to write generated test files
- --skip-existing: skip if a non-empty test file already exists (default)

Auto mapping used by `--target auto`:

- Python → `python:pytest`
- JavaScript → `javascript:jest`
- TypeScript → `typescript:jest`
- Go → `go:testing`
- Java → `java:junit5`
- Rust → `rust:cargo`

### run
Attempt to run generated tests for certain targets (best-effort).

```bash
unit-tester run [--target python:pytest] [--tests-dir .unit_tester/tests]
```

- Currently implemented: `python:pytest` (invokes `pytest` quietly and streams output)
- For other languages, run the appropriate test runner in your environment

### bdd-plan
Analyze a codebase and produce higher-level BDD feature specs (JSON), plus a survey.

```bash
unit-tester bdd-plan PATH \
  [--out-dir .unit_tester/bdd] \
  [--include-langs python javascript typescript go java rust] \
  [--model <openai-model>] \
  [--skip-existing / --no-skip-existing]
```

Writes `survey.json` and `features.json` in the output directory.

### bdd-render
Render BDD features into Gherkin `.feature` files.

```bash
unit-tester bdd-render [BDD_JSON] [--out-dir .unit_tester/bdd/features] \
  [--skip-existing / --no-skip-existing]
```

- BDD_JSON: path to the BDD features JSON (default `.unit_tester/bdd/features.json`)

## Configuration

Configuration is loaded from environment variables (and `./.env` if present) using Pydantic Settings.

Environment variables (defaults shown):

- OPENAI_API_KEY (required): your API key
- OPENAI_BASE_URL (optional): override base URL
- OPENAI_MODEL (default: `gpt-5-nano`)
- REQUEST_TIMEOUT_S (default: `60.0`)
- PLANNER_CONCURRENCY (default: `3`)
- IGNORE_GLOBS (optional): comma-separated globs to ignore during discovery; by default includes:
  - `**/.git/**`, `**/.venv/**`, `**/node_modules/**`, `**/dist/**`, `**/build/**`, `**/.unit_tester/**`

Example `.env`:

```dotenv
OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MODEL=gpt-5-nano
# REQUEST_TIMEOUT_S=60
# PLANNER_CONCURRENCY=3
```

## How it works (high-level)

1. Discover public API symbols in the specified path, honoring ignore globs
2. Plan test specs via the LLM with concurrency and progress updates
3. Render executable tests for your chosen target(s)
4. Optionally run the tests (Python/pytest supported today)

## Tips

- If you see "No spec files found", ensure you ran `plan` into the same `--out-dir` you are rendering from, or pass the correct directory to `render`.
- If discovery finds too few/many symbols, adjust `--include-langs` or `IGNORE_GLOBS`.
- Use `--no-skip-existing` to force re-planning or re-rendering.

## Development

From source:

```bash
# Clone and install in editable mode
pip install -e .

# Run the CLI from source
unit-tester --help | cat
```

## License

MIT


