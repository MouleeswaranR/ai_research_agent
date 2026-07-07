"""AST export extractor – parses top-level exports from code."""

from __future__ import annotations

import ast
import re

from app.schemas.graph import Symbol, SymbolKind


def extract_python_exports(code: str) -> list[Symbol]:
    """Extract top-level functions, classes, and public constants via Python AST."""
    symbols: list[Symbol] = []
    try:
        tree = ast.parse(code)
    except Exception:
        return symbols

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                symbols.append(Symbol(name=node.name, kind=SymbolKind.FUNCTION))
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                symbols.append(Symbol(name=node.name, kind=SymbolKind.CLASS))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_") and target.id.isupper():
                    symbols.append(Symbol(name=target.id, kind=SymbolKind.CONST))
    return symbols


def extract_js_ts_exports(code: str) -> list[Symbol]:
    """Extract exports via regex fallback for JS/TS (approximate parse)."""
    symbols: list[Symbol] = []
    # Match export function/class/const/let/var
    pattern = r"export\s+(async\s+)?(function|class|const|let|var|type|interface)\s+([A-Za-z0-9_]+)"
    for match in re.finditer(pattern, code):
        kw_kind = match.group(2)
        name = match.group(3)

        kind_map = {
            "function": SymbolKind.FUNCTION,
            "class": SymbolKind.CLASS,
            "const": SymbolKind.CONST,
            "type": SymbolKind.TYPE,
            "interface": SymbolKind.TYPE,
        }
        kind = kind_map.get(kw_kind, SymbolKind.DEFAULT)
        symbols.append(Symbol(name=name, kind=kind))

    if re.search(r"export\s+default\b", code) and not any(s.name == "default" for s in symbols):
        symbols.append(Symbol(name="default", kind=SymbolKind.DEFAULT))

    return symbols


def extract_exports_via_ast(code: str, language: str | None) -> list[Symbol]:
    """Extract symbols exported by code file depending on language."""
    if not code or not language:
        return []

    lang = language.lower().strip()
    if lang in ("python", "py"):
        return extract_python_exports(code)
    elif lang in ("typescript", "javascript", "ts", "js", "tsx", "jsx"):
        return extract_js_ts_exports(code)

    return []
