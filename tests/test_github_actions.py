"""Unit tests for agent/github_actions.py."""

from unittest.mock import MagicMock, patch
from agent.github_actions import (
    MARKER,
    apply_risk_label,
    find_existing_comment,
    generate_pytest_command,
    post_or_update_comment,
    request_reviewers,
    run_github_action,
)


def test_generate_pytest_command():
    tests = [
        {"test": "test_1", "file": "tests/test_a.py"},
        {"test": "test_2", "file": "tests/test_b.py"},
        {"test": "test_3", "file": "tests/test_a.py"},
    ]
    cmd = generate_pytest_command(tests)
    assert cmd == "pytest tests/test_a.py tests/test_b.py"

    empty_cmd = generate_pytest_command([])
    assert "Finding: No test reaches this change" in empty_cmd


def test_find_existing_comment():
    pr = MagicMock()
    c1 = MagicMock(body="Regular comment")
    c2 = MagicMock(body=f"Previous report {MARKER} details")
    pr.get_issue_comments.return_value = [c1, c2]

    found = find_existing_comment(pr)
    assert found == c2


def test_post_or_update_comment_update():
    pr = MagicMock()
    existing = MagicMock(id=999, body=f"Old report {MARKER}")
    pr.get_issue_comments.return_value = [existing]

    res = post_or_update_comment(pr, "New body", dry_run=False)
    existing.edit.assert_called_once_with("New body")
    assert res == "updated_comment_999"


def test_post_or_update_comment_create():
    pr = MagicMock()
    pr.get_issue_comments.return_value = []
    created = MagicMock(id=1001)
    pr.create_issue_comment.return_value = created

    res = post_or_update_comment(pr, "New body", dry_run=False)
    pr.create_issue_comment.assert_called_once_with("New body")
    assert res == "created_comment_1001"


def test_post_or_update_comment_dry_run():
    pr = MagicMock()
    res = post_or_update_comment(pr, "New body", dry_run=True)
    assert res == "dry_run_comment_skipped"
    pr.create_issue_comment.assert_not_called()


def test_apply_risk_label():
    pr = MagicMock()
    res = apply_risk_label(pr, "HIGH", dry_run=False)
    pr.as_issue().add_to_labels.assert_called_once_with("risk:high")
    assert res == "applied_risk:high"


def test_request_reviewers_collaborators():
    pr = MagicMock()
    repo = MagicMock()
    repo.has_in_collaborators.side_effect = lambda u: u == "alice"
    reviewers = [{"author": "alice"}, {"author": "bob"}]

    requested = request_reviewers(pr, repo, reviewers, dry_run=False)
    assert requested == ["alice"]
    pr.create_review_request.assert_called_once_with(reviewers=["alice"])


def test_run_github_action_dry_run():
    mock_client = MagicMock()
    with patch("agent.github_actions.run_impact_agent") as mock_agent:
        mock_agent.return_value = {
            "risk": {"score": 0.42, "label": "medium"},
            "affected_tests": [{"file": "tests/test_x.py"}],
            "reviewers": [{"author": "charlie"}],
        }
        res = run_github_action(
            repo_name="borgbase/vorta",
            pr_number=10,
            dry_run=True,
            client=mock_client,
        )
        assert res["dry_run"] is True
        assert res["risk_label"] == "medium"
        assert res["comment_status"] == "dry_run_comment_skipped"
