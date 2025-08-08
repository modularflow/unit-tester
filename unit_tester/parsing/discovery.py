from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable, List

from pathspec import PathSpec

from ..models import APISymbol


SUPPORTED_LANGS = {"python", "javascript", "typescript", "go", "java", "rust"}


def _build_ignore_spec(ignore_globs: List[str]) -> PathSpec:
    return PathSpec.from_lines("gitwildmatch", ignore_globs)


def discover_public_api(root: Path, include_langs: List[str], ignore_globs: List[str]) -> List[APISymbol]:
    include = set(lang.lower() for lang in include_langs) & SUPPORTED_LANGS
    ignore_spec = _build_ignore_spec(ignore_globs)
    symbols: List[APISymbol] = []

    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if ignore_spec.match_file(str(rel)):
            continue
        if path.is_dir():
            continue

        if path.suffix == ".py" and "python" in include:
            symbols.extend(_discover_python(path))
        elif path.suffix in {".js", ".mjs", ".cjs"} and "javascript" in include:
            symbols.extend(_discover_javascript(path))
        elif path.suffix in {".ts", ".tsx"} and "typescript" in include:
            symbols.extend(_discover_typescript(path))
        elif path.suffix == ".go" and "go" in include:
            symbols.extend(_discover_go(path))
        elif path.suffix == ".java" and "java" in include:
            symbols.extend(_discover_java(path))
        elif path.suffix == ".rs" and "rust" in include:
            symbols.extend(_discover_rust(path))

    return symbols


def _discover_python(file_path: Path) -> List[APISymbol]:
    source = file_path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(source)
    except Exception:
        return []

    module_qual = file_path.stem
    symbols: List[APISymbol] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if node.name.startswith("_"):
                continue
            sig = f"def {node.name}({', '.join(arg.arg for arg in node.args.args)})"
            doc = ast.get_docstring(node)
            symbols.append(
                APISymbol(
                    name=node.name,
                    qualified_name=f"{module_qual}.{node.name}",
                    kind="function",
                    language="python",
                    file_path=str(file_path),
                    signature=sig,
                    docstring=doc,
                )
            )
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            doc = ast.get_docstring(node)
            symbols.append(
                APISymbol(
                    name=node.name,
                    qualified_name=f"{module_qual}.{node.name}",
                    kind="class",
                    language="python",
                    file_path=str(file_path),
                    signature=f"class {node.name}",
                    docstring=doc,
                )
            )
            for member in node.body:
                if isinstance(member, ast.FunctionDef) and not member.name.startswith("_"):
                    sig = f"def {member.name}({', '.join(arg.arg for arg in member.args.args)})"
                    mdoc = ast.get_docstring(member)
                    symbols.append(
                        APISymbol(
                            name=member.name,
                            qualified_name=f"{module_qual}.{node.name}.{member.name}",
                            kind="method",
                            language="python",
                            file_path=str(file_path),
                            signature=sig,
                            docstring=mdoc,
                        )
                    )
    return symbols


def _discover_javascript(file_path: Path) -> List[APISymbol]:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    symbols: List[APISymbol] = []
    for m in re.finditer(r"export\s+function\s+(\w+)\s*\(([^)]*)\)", text):
        name = m.group(1)
        if name.startswith("_"):
            continue
        symbols.append(
            APISymbol(
                name=name,
                qualified_name=f"{file_path.stem}.{name}",
                kind="function",
                language="javascript",
                file_path=str(file_path),
                signature=f"function {name}({m.group(2)})",
            )
        )
    for m in re.finditer(r"export\s+class\s+(\w+)", text):
        name = m.group(1)
        if name.startswith("_"):
            continue
        symbols.append(
            APISymbol(
                name=name,
                qualified_name=f"{file_path.stem}.{name}",
                kind="class",
                language="javascript",
                file_path=str(file_path),
                signature=f"class {name}",
            )
        )
    return symbols


def _discover_typescript(file_path: Path) -> List[APISymbol]:
    # Reuse JS heuristics
    return _discover_javascript(file_path)


def _discover_go(file_path: Path) -> List[APISymbol]:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    symbols: List[APISymbol] = []
    for m in re.finditer(r"func\s+(\w+)\s*\(([^)]*)\)", text):
        name = m.group(1)
        if name and name[0].islower():  # unexported in Go start with lowercase
            continue
        symbols.append(
            APISymbol(
                name=name,
                qualified_name=f"{file_path.stem}.{name}",
                kind="function",
                language="go",
                file_path=str(file_path),
                signature=f"func {name}({m.group(2)})",
            )
        )
    for m in re.finditer(r"type\s+(\w+)\s+struct\s*\{", text):
        name = m.group(1)
        if name and name[0].islower():
            continue
        symbols.append(
            APISymbol(
                name=name,
                qualified_name=f"{file_path.stem}.{name}",
                kind="class",
                language="go",
                file_path=str(file_path),
                signature=f"type {name} struct",
            )
        )
    return symbols


def _discover_java(file_path: Path) -> List[APISymbol]:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    symbols: List[APISymbol] = []
    for m in re.finditer(r"public\s+class\s+(\w+)", text):
        name = m.group(1)
        symbols.append(
            APISymbol(
                name=name,
                qualified_name=f"{file_path.stem}.{name}",
                kind="class",
                language="java",
                file_path=str(file_path),
                signature=f"public class {name}",
            )
        )
    for m in re.finditer(r"public\s+static\s+\w+[\[\]]*\s+(\w+)\s*\(([^)]*)\)", text):
        name = m.group(1)
        symbols.append(
            APISymbol(
                name=name,
                qualified_name=f"{file_path.stem}.{name}",
                kind="function",
                language="java",
                file_path=str(file_path),
                signature=f"public static {name}({m.group(2)})",
            )
        )
    return symbols


def _discover_rust(file_path: Path) -> List[APISymbol]:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    symbols: List[APISymbol] = []

    # Top-level public functions
    for m in re.finditer(r"\bpub\s+fn\s+(\w+)\s*\(([^)]*)\)", text):
        name = m.group(1)
        symbols.append(
            APISymbol(
                name=name,
                qualified_name=f"{file_path.stem}.{name}",
                kind="function",
                language="rust",
                file_path=str(file_path),
                signature=f"pub fn {name}({m.group(2)})",
            )
        )

    # Public structs and enums
    for m in re.finditer(r"\bpub\s+struct\s+(\w+)", text):
        name = m.group(1)
        symbols.append(
            APISymbol(
                name=name,
                qualified_name=f"{file_path.stem}.{name}",
                kind="class",
                language="rust",
                file_path=str(file_path),
                signature=f"pub struct {name}",
            )
        )
    for m in re.finditer(r"\bpub\s+enum\s+(\w+)", text):
        name = m.group(1)
        symbols.append(
            APISymbol(
                name=name,
                qualified_name=f"{file_path.stem}.{name}",
                kind="class",
                language="rust",
                file_path=str(file_path),
                signature=f"pub enum {name}",
            )
        )

    # Methods in impl blocks
    for impl in re.finditer(r"\bimpl(?:\s*<[^>]+>)?\s+(\w+)\s*\{([\s\S]*?)\}", text):
        type_name = impl.group(1)
        block = impl.group(2)
        for m in re.finditer(r"\bpub\s+fn\s+(\w+)\s*\(", block):
            meth = m.group(1)
            symbols.append(
                APISymbol(
                    name=meth,
                    qualified_name=f"{file_path.stem}.{type_name}.{meth}",
                    kind="method",
                    language="rust",
                    file_path=str(file_path),
                    signature=f"pub fn {meth}(...)",
                )
            )

    return symbols


