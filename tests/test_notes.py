"""Notes extraction and grounding (no network)."""

from agent.agent import _extract_notes, _grounded

F = "\x60" * 3
DUMP = f"""### Tool Outcomes
- map_diff_to_functions: answered_with_path
---
{F}json
{{ "summary": "Changes src.a.f; 13 callers.", "section_notes": {{"blast": "13 callers"}} }}
{F}"""


def test_extracts_json_summary_from_markdown_dump():
    d = _extract_notes(DUMP)
    assert d["summary"] == "Changes src.a.f; 13 callers."
    assert "###" not in d["summary"]


def test_plain_text_without_json_gives_no_notes():
    assert _extract_notes("just prose, no json here") is None


def test_invalid_json_gives_no_notes():
    assert _extract_notes("{not valid json}") is None


def test_name_followed_by_full_stop_is_still_grounded():
    assert _grounded("It changes src.a.f.", '{"changed": ["src.a.f"]}')


def test_unknown_name_is_not_grounded():
    assert not _grounded("It breaks src.zzz.ghost.", '{"changed": ["src.a.f"]}')
