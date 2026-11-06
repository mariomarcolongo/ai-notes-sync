import json

from ai_notes_sync.relay import Recorder, paths_from_result


def rpc(**kw):
    return json.dumps({"jsonrpc": "2.0", **kw}).encode()


def result(i, text, error=False):
    return rpc(id=i, result={"content": [{"type": "text", "text": text}], "isError": error})


def test_records_write_with_client_and_self_report(tmp_path):
    log = tmp_path / "edits.jsonl"
    rec = Recorder("cursor", log, clock=lambda: 0)
    rec.on_request(rpc(id=1, method="initialize", params={"clientInfo": {"name": "Cursor", "version": "3.1"}}))
    rec.on_request(rpc(id=2, method="tools/call", params={"name": "bm_write", "arguments": {
        "title": "Plan", "directory": "notes/projects",
        "metadata": {"model": "gpt-x", "reasoning_effort": "high", "color": "ignored"}}}))
    rec.on_response(result(2, "Created notes/projects/My plan.md\ntitle: Plan"))

    e = json.loads(log.read_text())
    assert e["app"] == "cursor" and e["client"] == "Cursor" and e["client_version"] == "3.1"
    assert e["model"] == "gpt-x"
    assert e["self_reported"] == {"model": "gpt-x", "reasoning_effort": "high"}
    assert e["paths"] == ["notes/projects/My plan.md"]
    assert e["ok"] is True


def test_ignores_reads_and_marks_errors(tmp_path):
    log = tmp_path / "edits.jsonl"
    rec = Recorder("x", log)
    rec.on_request(rpc(id=1, method="tools/call", params={"name": "bm_search", "arguments": {}}))
    assert rec.on_response(result(1, "Results")) is None
    rec.on_request(rpc(id=2, method="tools/call", params={"name": "bm_edit", "arguments": {"identifier": "a.md"}}))
    rec.on_response(result(2, "note not found", error=True))
    e = json.loads(log.read_text())
    assert e["ok"] is False and e["paths"] == []


def test_ignores_garbage():
    rec = Recorder("x", None)
    rec.on_request(b"not json")
    rec.on_request(b"[1, 2]")
    assert rec.on_response(b"{}") is None


def test_paths_from_result():
    assert paths_from_result("Edited notes/a b.md (append)\nchecksum: 1") == ["notes/a b.md"]
    assert paths_from_result("Moved notes/a.md to archive/a.md") == ["archive/a.md", "notes/a.md"]
    assert paths_from_result("Deleted notes/old.md") == ["notes/old.md"]
    assert paths_from_result("Something else") == []
