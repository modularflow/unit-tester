from __future__ import annotations

from typing import List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..config import AppConfig
from ..llm.client import LLMClient
from ..models import NLTestSpec, RenderedTest, TargetSpec


RENDER_SYSTEM = (
    "You are a senior engineer generating high-quality, idiomatic unit tests. "
    "Follow best practices of the target language and framework, create isolated tests, "
    "use clear Arrange-Act-Assert structure, and avoid mocking internal implementation details."
)


TARGET_HINTS = {
    ("python", "pytest"): "Use pytest style functions, fixtures when needed, prefer parametrize for partitions.",
    ("javascript", "jest"): "Use Jest tests with describe/it, async/await for async, and expect APIs.",
    ("typescript", "jest"): "Use TypeScript with Jest and proper types; include imports and describe/it blocks.",
    ("go", "testing"): "Use Go's testing package with table-driven tests and t.Run for subtests.",
    ("java", "junit5"): "Use JUnit 5 with @Test, Assertions.*; assume Maven/Gradle project structure.",
    ("rust", "cargo"): "Use Rust built-in test framework with #[cfg(test)] mod tests, #[test] functions, assert!/assert_eq!, and cargo test.",
}


def _build_render_prompt(spec: NLTestSpec, target: TargetSpec) -> str:
    hint = TARGET_HINTS.get((target.language, target.framework), "")
    cases_json = spec.model_dump_json(indent=2)
    return f"""
Generate executable unit tests for the following symbol based on the provided natural-language test plan.

Target: {target.language}:{target.framework}
Guidance: {hint}

Constraints:
- Prefer readability and coverage
- Cover the provided cases faithfully
- Add necessary imports and minimal scaffolding
- Do not include explanations, only test code

Test plan (JSON):
{cases_json}
""".strip()


def render_tests(
    specs: List[NLTestSpec],
    target: TargetSpec,
    config: AppConfig,
    progress_callback: Optional[Callable[[int, int, NLTestSpec], None]] = None,
    test_callback: Optional[Callable[[int, int, RenderedTest], None]] = None,
) -> List[RenderedTest]:
    def do_render(idx: int, spec: NLTestSpec) -> tuple[int, RenderedTest]:
        client = LLMClient(config)
        prompt = _build_render_prompt(spec, target)
        # Use temperature=1.0 to satisfy models that only accept default temperature
        code = client.complete(prompt, system=RENDER_SYSTEM, temperature=1.0)
        if "```" in code:
            first = code.find("```")
            rest = code[first + 3 :]
            lang_tag_end = rest.find("\n")
            if lang_tag_end != -1:
                rest = rest[lang_tag_end + 1 :]
            second = rest.find("```")
            if second != -1:
                code = rest[:second].strip()
        return idx, RenderedTest(spec=spec, target=target, content=code)

    total = len(specs)
    rendered: List[RenderedTest] = [None] * total  # type: ignore
    completed = 0

    with ThreadPoolExecutor(max_workers=max(1, getattr(config, "renderer_concurrency", 3))) as executor:
        future_to_info = {executor.submit(do_render, idx, spec): (idx, spec) for idx, spec in enumerate(specs)}
        for future in as_completed(future_to_info):
            orig_idx, spec = future_to_info[future]
            try:
                idx, test = future.result()
            except Exception:
                idx, test = orig_idx, RenderedTest(spec=spec, target=target, content="")
            rendered[idx] = test
            completed += 1
            if test_callback:
                try:
                    test_callback(completed, total, test)
                except Exception:
                    pass
            if progress_callback:
                try:
                    progress_callback(completed, total, spec)
                except Exception:
                    pass

    return [t for t in rendered if t is not None]


