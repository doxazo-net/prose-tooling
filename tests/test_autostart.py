"""Tests for hook-triggered server auto-start.

If the LanguageTool container is stopped, the client starts it (via the server
script) and retries, rather than failing the commit. The network/subprocess
I/O is injected so the decision logic is testable without a container.
"""

from prose_check import ensure_server


def test_does_not_start_when_already_up():
    started = []
    up = ensure_server("url", start_fn=lambda: started.append(1), is_up=lambda u: True)
    assert up is True
    assert started == []


def test_starts_when_down_then_becomes_up():
    state = {"up": False}

    def start():
        state["up"] = True

    up = ensure_server("url", start_fn=start, is_up=lambda u: state["up"])
    assert up is True


def test_returns_false_when_start_does_not_help():
    started = []
    up = ensure_server("url", start_fn=lambda: started.append(1), is_up=lambda u: False)
    assert up is False
    assert started == [1]  # start was attempted exactly once
