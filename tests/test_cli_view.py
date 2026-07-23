"""Tests for the `view` CLI command options."""

from __future__ import annotations

from click.testing import CliRunner

from inspect_dataset.cli import cli


def test_view_help_documents_reload():
    result = CliRunner().invoke(cli, ["view", "--help"])
    assert result.exit_code == 0
    assert "--reload" in result.output


def test_view_reload_uses_watchfiles(monkeypatch):
    """--reload hands the server to watchfiles.run_process instead of run_server."""
    calls: dict[str, object] = {}

    import watchfiles

    def fake_run_process(*paths, target, kwargs, watch_filter, callback):
        calls["paths"] = paths
        calls["target"] = target
        calls["kwargs"] = kwargs

    monkeypatch.setattr(watchfiles, "run_process", fake_run_process)

    result = CliRunner().invoke(cli, ["view", "--no-open", "--reload", "--port", "7777"])
    assert result.exit_code == 0, result.output

    from inspect_dataset._view.server import run_server

    assert calls["target"] is run_server
    assert calls["kwargs"] == {"findings_dirs": None, "port": 7777}
    # Watches the installed package directory
    assert str(calls["paths"][0]).endswith("inspect_dataset")
