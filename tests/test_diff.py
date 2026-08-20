import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.diff import diff_snapshots


def _rec(**kwargs):
    base = {
        "uid": "VXvue/VP-1",
        "id": "VP-1",
        "project_id": "VXvue",
        "title": "Sample",
        "status": "draft",
        "content_html": "<p>hello</p>",
        "severity": "normal",
        "priority": "50.0",
        "active": "active",
        "jira_id": None,
        "old_id": "01-10-10",
        "linked_work_items": [],
        "parent_id": None,
        "attachments_meta": [],
        "image_results": [],
        "comments": [],
    }
    base.update(kwargs)
    return base


def test_new_srs_detected():
    diffs = diff_snapshots({}, {"VXvue/VP-1": _rec()})
    assert len(diffs) == 1
    assert diffs[0].change_type == "new"


def test_deleted_srs_detected():
    diffs = diff_snapshots({"VXvue/VP-1": _rec()}, {})
    assert diffs[0].change_type == "deleted"


def test_unchanged_srs():
    rec = _rec()
    diffs = diff_snapshots({"VXvue/VP-1": rec}, {"VXvue/VP-1": dict(rec)})
    assert diffs[0].change_type == "unchanged"
    assert diffs[0].field_changes == []


def test_status_change_detected():
    prev = _rec(status="draft")
    curr = _rec(status="reviewed")
    diffs = diff_snapshots({"VXvue/VP-1": prev}, {"VXvue/VP-1": curr})
    assert "status" in diffs[0].field_changes
    assert diffs[0].status_before == "draft"
    assert diffs[0].status_after == "reviewed"


def test_description_text_change_produces_diff_lines():
    prev = _rec(content_html="<p>Detector shall reconnect automatically.</p>")
    curr = _rec(content_html="<p>Detector shall reconnect automatically within 10 seconds.</p>")
    diffs = diff_snapshots({"VXvue/VP-1": prev}, {"VXvue/VP-1": curr})
    assert "description" in diffs[0].field_changes
    assert any("10 seconds" in line for line in diffs[0].text_diff_lines)


def test_strikethrough_added_detected():
    prev = _rec(content_html="<p>keep this</p>")
    curr = _rec(content_html='<p><span style="text-decoration: line-through;">keep this</span></p>')
    diffs = diff_snapshots({"VXvue/VP-1": prev}, {"VXvue/VP-1": curr})
    assert "strikethrough_added" in diffs[0].field_changes


def test_underline_added_detected():
    prev = _rec(content_html="<p>keep this</p>")
    curr = _rec(content_html='<p><span style="text-decoration: underline;">keep this</span></p>')
    diffs = diff_snapshots({"VXvue/VP-1": prev}, {"VXvue/VP-1": curr})
    assert "underline_added" in diffs[0].field_changes


def test_linked_work_items_change_detected():
    prev = _rec(parent_id="VP-100")
    curr = _rec(parent_id="VP-200")
    diffs = diff_snapshots({"VXvue/VP-1": prev}, {"VXvue/VP-1": curr})
    assert "linked_work_items" in diffs[0].field_changes


def test_image_change_detected():
    prev = _rec(image_results=[{"filename": "a.png", "ok": True}])
    curr = _rec(image_results=[{"filename": "b.png", "ok": True}])
    diffs = diff_snapshots({"VXvue/VP-1": prev}, {"VXvue/VP-1": curr})
    assert "images" in diffs[0].field_changes


def test_comment_added_detected():
    prev = _rec(comments=[])
    curr = _rec(comments=[{"id": "c1", "text": "reviewed, looks good"}])
    diffs = diff_snapshots({"VXvue/VP-1": prev}, {"VXvue/VP-1": curr})
    assert "comments" in diffs[0].field_changes
