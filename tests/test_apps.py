import json

from ai_notes_sync import apps
from ai_notes_sync.apps import RULE_BEGIN, App, add_rule, configure
from conftest import write


def test_json_config_keeps_other_servers(tmp_path):
    p = write(tmp_path / "mcp.json", json.dumps({"mcpServers": {"other": {"command": "x"}}, "keep": 1}))
    app = App("cursor", "Cursor", p, "json")
    assert configure(app, apply=False).startswith("plan")
    assert json.loads(p.read_text())["mcpServers"].keys() == {"other"}  # dry run changed nothing

    assert configure(app, apply=True).startswith("done")
    data = json.loads(p.read_text())
    assert data["keep"] == 1 and "other" in data["mcpServers"]
    assert data["mcpServers"]["basic-memory"]["args"][-2:] == ["relay", "cursor"]
    assert list(tmp_path.glob("mcp.json.bak-*"))
    assert configure(app, apply=True).startswith("ok")


def test_vscode_uses_servers_key(tmp_path):
    app = App("vscode", "VS Code", tmp_path / "User/mcp.json", "vscode")
    configure(app, apply=True)
    entry = json.loads(app.config.read_text())["servers"]["basic-memory"]
    assert entry["type"] == "stdio"


def test_toml_block_is_replaced_not_duplicated(tmp_path):
    p = write(tmp_path / "config.toml", 'model = "m"\n\n[mcp_servers.basic-memory]\ncommand = "old"\n'
                                        '\n[mcp_servers.basic-memory.env]\nA = "1"\n\n[other]\nx = 1\n')
    configure(App("codex", "Codex", p, "toml"), apply=True)
    text = p.read_text()
    assert text.count("[mcp_servers.basic-memory]") == 1
    assert '"old"' not in text and "[other]" in text and 'model = "m"' in text
    assert '"relay", "codex"' in text


def test_rule_added_once_and_updated(tmp_path):
    p = write(tmp_path / "CLAUDE.md", "# Mine\n")
    add_rule("Claude", p, "", apply=True)
    add_rule("Claude", p, "", apply=True)
    assert p.read_text().count(RULE_BEGIN) == 1
    p.write_text(p.read_text().replace("Shared notes", "Old notes"))
    assert add_rule("Claude", p, "", apply=True).startswith("done")
    assert "Old notes" not in p.read_text() and p.read_text().startswith("# Mine")


def test_missing_apps_are_reported(cfg):
    out = apps.run(cfg, apply=False)
    assert "not installed" in out
