"""Unit tests for ingest.ast_parser."""

from ingest.ast_parser import (
    is_test_function,
    parse_python_source,
    parse_source_repo,
    path_to_module,
)

SAMPLE_APP = """
def helper():
    return 1

def caller():
    helper()
    other()

class Worker:
    def run(self):
        helper()
        self.finish()

    def finish(self):
        return helper()
"""

SAMPLE_OTHER = """
def other():
    return 2

def get():
    return 0
"""

SAMPLE_TEST = """
from app import helper

def test_helper():
    helper()

def setup_env():
    return True
"""


def test_path_to_module():
    """Verify dotted module names from repo-relative paths."""
    assert path_to_module("app.py") == "app"
    assert path_to_module("pkg/mod.py") == "pkg.mod"
    assert path_to_module("pkg/__init__.py") == "pkg"


def test_qnames_from_sample_source():
    """Verify module.function and module.Class.method qnames."""
    parsed = parse_python_source(SAMPLE_APP, "app.py")
    qnames = {fn.qname for fn in parsed.functions}
    assert qnames == {
        "app.helper",
        "app.caller",
        "app.Worker.run",
        "app.Worker.finish",
    }
    helper = next(fn for fn in parsed.functions if fn.name == "helper")
    assert helper.start >= 1
    assert helper.end >= helper.start


def test_calls_same_module_and_cross_module():
    """Verify CALLS: same-module preference and unique cross-module fallback."""
    graph = parse_source_repo(
        {
            "app.py": SAMPLE_APP,
            "other.py": SAMPLE_OTHER,
        }
    )
    call_pairs = {(c["caller"], c["callee"]) for c in graph.calls}
    assert ("app.caller", "app.helper") in call_pairs
    assert ("app.caller", "other.other") in call_pairs
    assert ("app.Worker.run", "app.helper") in call_pairs
    assert ("app.Worker.run", "app.Worker.finish") in call_pairs
    # builtins / common names like get() must be skipped
    assert not any(c["callee"].endswith(".get") for c in graph.calls)


def test_imported_call_resolution():
    """Verify from-import call resolves to the imported function."""
    graph = parse_source_repo(
        {
            "app.py": SAMPLE_APP,
            "tests/test_app.py": SAMPLE_TEST,
        }
    )
    call_pairs = {(c["caller"], c["callee"]) for c in graph.calls}
    assert ("tests.test_app.test_helper", "app.helper") in call_pairs
    imports = {(i["src"], i["dst"]) for i in graph.imports}
    assert ("tests/test_app.py", "app.py") in imports


def test_test_labeling():
    """Test label only for test_* functions under tests/."""
    graph = parse_source_repo(
        {
            "app.py": "def test_not_here():\n    pass\n",
            "tests/test_app.py": SAMPLE_TEST,
        }
    )
    by_qname = {f["qname"]: f for f in graph.functions}
    assert by_qname["tests.test_app.test_helper"]["is_test"] is True
    assert by_qname["tests.test_app.setup_env"]["is_test"] is False
    assert by_qname["app.test_not_here"]["is_test"] is False
    assert is_test_function("test_helper", "tests/test_app.py") is True
    assert is_test_function("test_helper", "app.py") is False
