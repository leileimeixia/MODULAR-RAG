"""Tests for the dashboard launcher script."""

from __future__ import annotations

import subprocess

from scripts import start_dashboard


def test_start_dashboard_builds_streamlit_command(monkeypatch) -> None:
    calls = []

    def fake_call(command, cwd):
        calls.append((command, cwd))
        return 7

    monkeypatch.setattr(subprocess, "call", fake_call)

    exit_code = start_dashboard.main(["--server.port", "8502"])

    assert exit_code == 7
    command, cwd = calls[0]
    assert command[:4] == [
        start_dashboard.sys.executable,
        "-m",
        "streamlit",
        "run",
    ]
    assert command[-2:] == ["--server.port", "8502"]
    assert command[4].endswith("src\\observability\\dashboard\\app.py")
    assert cwd == start_dashboard.Path(__file__).resolve().parents[2]
