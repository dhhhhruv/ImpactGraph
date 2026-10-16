"""AST extraction of File/Function nodes and CALLS/IMPORTS/DEFINES edges."""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

SKIP_CALL_NAMES: Set[str] = {
    "get",
    "set",
    "append",
    "items",
    "update",
} | {n for n in dir(builtins) if not n.startswith("_")}

BATCH_SIZE = 500


@dataclass
class FunctionInfo:
    """One Function (and optional Test) node."""

    qname: str
    name: str
    file: str
    start: int
    end: int
    is_test: bool


@dataclass
class FileParse:
    """Per-file parse output before repo-wide call resolution."""

    path: str
    loc: int
    module: str
    functions: List[FunctionInfo] = field(default_factory=list)
    raw_calls: List[Tuple[str, str]] = field(default_factory=list)
    import_names: Dict[str, str] = field(default_factory=dict)
    import_modules: List[str] = field(default_factory=list)


@dataclass
class RepoGraph:
    """Resolved graph fragments ready for FalkorDB load."""

    files: List[Dict[str, object]]
    functions: List[Dict[str, object]]
    defines: List[Dict[str, str]]
    calls: List[Dict[str, str]]
    imports: List[Dict[str, str]]


def path_to_module(rel_path: str) -> str:
    """Convert repo-relative .py path to dotted module qname prefix."""
    norm = rel_path.replace("\\", "/")
    if norm.endswith(".py"):
        norm = norm[:-3]
    if norm.endswith("/__init__"):
        norm = norm[: -len("/__init__")]
    return norm.replace("/", ".")


def is_tests_path(file_path: str) -> bool:
    """True when path is under a tests/ directory."""
    parts = Path(file_path.replace("\\", "/")).parts
    return "tests" in parts


def is_test_function(name: str, file_path: str) -> bool:
    """Test label: name starts with test_ and file lives under tests/."""
    return name.startswith("test_") and is_tests_path(file_path)


def _func_end(node: ast.AST) -> int:
    """Best-effort end lineno for a function/class body node."""
    end = getattr(node, "end_lineno", None)
    if isinstance(end, int):
        return end
    return int(getattr(node, "lineno", 1))


def _call_basename(node: ast.Call) -> Optional[str]:
    """Extract the callable's simple name from a Call node."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _collect_calls(fn_node: ast.AST, caller_qname: str) -> List[Tuple[str, str]]:
    """Walk a function body and collect (caller_qname, call_basename) pairs."""
    found: List[Tuple[str, str]] = []
    for child in ast.walk(fn_node):
        if not isinstance(child, ast.Call):
            continue
        name = _call_basename(child)
        if name is None or name in SKIP_CALL_NAMES:
            continue
        found.append((caller_qname, name))
    return found


def _record_function(
    node: ast.AST,
    name: str,
    qname: str,
    file_path: str,
    out: FileParse,
) -> None:
    """Append FunctionInfo and its raw calls to a FileParse."""
    info = FunctionInfo(
        qname=qname,
        name=name,
        file=file_path,
        start=int(getattr(node, "lineno", 1)),
        end=_func_end(node),
        is_test=is_test_function(name, file_path),
    )
    out.functions.append(info)
    out.raw_calls.extend(_collect_calls(node, qname))


def _handle_import(node: ast.Import, out: FileParse) -> None:
    """Record import module aliases from an Import statement."""
    for alias in node.names:
        mod = alias.name
        local = alias.asname or mod.split(".")[0]
        out.import_names[local] = mod
        out.import_modules.append(mod)


def _handle_import_from(node: ast.ImportFrom, out: FileParse) -> None:
    """Record from-import bindings; skip relative and star imports."""
    if (node.level and node.level > 0) or not node.module:
        return
    module = node.module
    out.import_modules.append(module)
    for alias in node.names:
        if alias.name == "*":
            continue
        local = alias.asname or alias.name
        out.import_names[local] = f"{module}.{alias.name}"


def _visit_class(
    node: ast.ClassDef,
    module: str,
    file_path: str,
    out: FileParse,
) -> None:
    """Visit methods of a class (one nesting level)."""
    class_q = f"{module}.{node.name}"
    for child in node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qname = f"{class_q}.{child.name}"
            _record_function(child, child.name, qname, file_path, out)


def _visit_module_body(
    tree: ast.AST,
    module: str,
    file_path: str,
    out: FileParse,
) -> None:
    """Visit top-level imports, functions, and classes in a module."""
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.Import):
            _handle_import(node, out)
        elif isinstance(node, ast.ImportFrom):
            _handle_import_from(node, out)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qname = f"{module}.{node.name}"
            _record_function(node, node.name, qname, file_path, out)
        elif isinstance(node, ast.ClassDef):
            _visit_class(node, module, file_path, out)


def parse_python_source(
    source: str,
    file_path: str,
    module: Optional[str] = None,
) -> FileParse:
    """Parse one Python source string into functions, calls, and imports."""
    mod = module if module is not None else path_to_module(file_path)
    loc = source.count("\n") + (0 if source.endswith("\n") else 1) if source else 0
    out = FileParse(path=file_path, loc=loc, module=mod)
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return out
    _visit_module_body(tree, mod, file_path, out)
    return out


def parse_file(path: Path, repo_root: Path) -> FileParse:
    """Parse a .py file relative to repo_root."""
    rel = str(path.relative_to(repo_root)).replace("\\", "/")
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_python_source(text, rel, path_to_module(rel))


def iter_python_files(repo_root: Path) -> Iterable[Path]:
    """Yield .py files under repo_root, skipping common junk dirs."""
    skip = {".git", ".venv", "venv", "__pycache__", "node_modules", ".tox"}
    for p in repo_root.rglob("*.py"):
        if any(part in skip for part in p.parts):
            continue
        yield p


def parse_repo(repo_root: Path | str) -> RepoGraph:
    """Walk a repo, resolve calls, and return load-ready graph fragments."""
    root = Path(repo_root)
    parses = [parse_file(p, root) for p in iter_python_files(root)]
    return resolve_repo(parses, root)


def _build_indexes(
    parses: List[FileParse],
) -> Tuple[
    Dict[str, Dict[str, List[str]]],
    Dict[str, List[str]],
    Dict[str, str],
]:
    """Build module→name→qnames, name→qnames, and module→file indexes."""
    by_module: Dict[str, Dict[str, List[str]]] = {}
    by_name: Dict[str, List[str]] = {}
    module_file: Dict[str, str] = {}
    for fp in parses:
        module_file[fp.module] = fp.path
        bucket = by_module.setdefault(fp.module, {})
        for fn in fp.functions:
            bucket.setdefault(fn.name, []).append(fn.qname)
            by_name.setdefault(fn.name, []).append(fn.qname)
    return by_module, by_name, module_file


def _resolve_import_target(
    binding: str,
    by_module: Dict[str, Dict[str, List[str]]],
    by_name: Dict[str, List[str]],
) -> Optional[str]:
    """Map an import binding like pkg.mod.func to a Function qname if unique."""
    if "." in binding:
        mod, name = binding.rsplit(".", 1)
        cands = by_module.get(mod, {}).get(name, [])
        if len(cands) == 1:
            return cands[0]
        if len(cands) > 1:
            return None
    cands = by_name.get(binding.split(".")[-1], [])
    if len(cands) == 1:
        return cands[0]
    return None


def _same_module_callee(
    module: str,
    name: str,
    caller_qname: str,
    by_module: Dict[str, Dict[str, List[str]]],
) -> Optional[str]:
    """Prefer a unique same-module callee; bias toward same class."""
    cands = by_module.get(module, {}).get(name, [])
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    parent = caller_qname.rsplit(".", 1)[0]
    same = [c for c in cands if c.rsplit(".", 1)[0] == parent]
    if len(same) == 1:
        return same[0]
    return None


def _resolve_one_call(
    module: str,
    caller: str,
    name: str,
    import_names: Dict[str, str],
    by_module: Dict[str, Dict[str, List[str]]],
    by_name: Dict[str, List[str]],
) -> List[str]:
    """Resolve a raw call name via same-module, import, then <=3 global."""
    if name in SKIP_CALL_NAMES:
        return []
    same = _same_module_callee(module, name, caller, by_module)
    if same:
        return [same]
    if name in import_names:
        target = _resolve_import_target(import_names[name], by_module, by_name)
        if target:
            return [target]
    global_cands = by_name.get(name, [])
    if 1 <= len(global_cands) <= 3:
        return list(global_cands)
    return []


def _module_to_file(
    module_name: str,
    module_file: Dict[str, str],
) -> Optional[str]:
    """Map a dotted import module to a known repo file path."""
    if module_name in module_file:
        return module_file[module_name]
    parts = module_name.split(".")
    for i in range(len(parts), 0, -1):
        key = ".".join(parts[:i])
        if key in module_file:
            return module_file[key]
    return None


def _emit_functions(
    fp: FileParse,
    functions: List[Dict[str, object]],
    defines: List[Dict[str, str]],
) -> None:
    """Append function node dicts and DEFINES edges for one file."""
    for fn in fp.functions:
        functions.append(
            {
                "qname": fn.qname,
                "name": fn.name,
                "file": fn.file,
                "start": fn.start,
                "end": fn.end,
                "is_test": fn.is_test,
            }
        )
        defines.append({"file": fn.file, "qname": fn.qname})


def _emit_calls(
    fp: FileParse,
    by_module: Dict[str, Dict[str, List[str]]],
    by_name: Dict[str, List[str]],
    calls: List[Dict[str, str]],
    call_seen: Set[Tuple[str, str]],
) -> None:
    """Resolve and append CALLS edges for one file's raw calls."""
    for caller, name in fp.raw_calls:
        for callee in _resolve_one_call(
            fp.module, caller, name, fp.import_names, by_module, by_name
        ):
            key = (caller, callee)
            if key in call_seen or caller == callee:
                continue
            call_seen.add(key)
            calls.append({"caller": caller, "callee": callee})


def _emit_imports(
    fp: FileParse,
    module_file: Dict[str, str],
    imports: List[Dict[str, str]],
    import_seen: Set[Tuple[str, str]],
) -> None:
    """Append IMPORTS edges from one file to resolved imported files."""
    for mod in fp.import_modules:
        dst = _module_to_file(mod, module_file)
        if dst is None or dst == fp.path:
            continue
        ikey = (fp.path, dst)
        if ikey in import_seen:
            continue
        import_seen.add(ikey)
        imports.append({"src": fp.path, "dst": dst})


def resolve_repo(parses: List[FileParse], repo_root: Path | str | None = None) -> RepoGraph:
    """Resolve raw calls and imports across already-parsed files."""
    del repo_root  # reserved for future path normalization
    by_module, by_name, module_file = _build_indexes(parses)
    files: List[Dict[str, object]] = []
    functions: List[Dict[str, object]] = []
    defines: List[Dict[str, str]] = []
    calls: List[Dict[str, str]] = []
    imports: List[Dict[str, str]] = []
    call_seen: Set[Tuple[str, str]] = set()
    import_seen: Set[Tuple[str, str]] = set()
    for fp in parses:
        files.append({"path": fp.path, "loc": fp.loc})
        _emit_functions(fp, functions, defines)
        _emit_calls(fp, by_module, by_name, calls, call_seen)
        _emit_imports(fp, module_file, imports, import_seen)
    return RepoGraph(
        files=files,
        functions=functions,
        defines=defines,
        calls=calls,
        imports=imports,
    )


def parse_source_repo(sources: Dict[str, str]) -> RepoGraph:
    """Parse an in-memory path→source map (used by unit tests)."""
    parses = [
        parse_python_source(src, path, path_to_module(path))
        for path, src in sorted(sources.items())
    ]
    return resolve_repo(parses)
