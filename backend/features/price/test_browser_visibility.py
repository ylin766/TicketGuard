"""Tests for the cross-platform off-screen browser strategy router."""

from __future__ import annotations

from backend.features.price import browser_visibility


def test_onscreen_override_returns_no_args(monkeypatch):
    monkeypatch.setenv("PRICE_BROWSER_ONSCREEN", "1")
    assert browser_visibility.offscreen_launch_args() == []


def test_windows_uses_new_headless(monkeypatch):
    monkeypatch.delenv("PRICE_BROWSER_ONSCREEN", raising=False)
    monkeypatch.setattr(browser_visibility.sys, "platform", "win32")
    assert browser_visibility.offscreen_launch_args() == ["--headless=new"]


def test_macos_parks_window_offscreen(monkeypatch):
    monkeypatch.delenv("PRICE_BROWSER_ONSCREEN", raising=False)
    monkeypatch.setattr(browser_visibility.sys, "platform", "darwin")
    assert browser_visibility.offscreen_launch_args() == [
        "--window-position=-32000,-32000"
    ]


def test_linux_parks_window_offscreen(monkeypatch):
    monkeypatch.delenv("PRICE_BROWSER_ONSCREEN", raising=False)
    monkeypatch.setattr(browser_visibility.sys, "platform", "linux")
    assert browser_visibility.offscreen_launch_args() == [
        "--window-position=-32000,-32000"
    ]


def test_onscreen_override_wins_over_platform(monkeypatch):
    monkeypatch.setenv("PRICE_BROWSER_ONSCREEN", "1")
    monkeypatch.setattr(browser_visibility.sys, "platform", "win32")
    assert browser_visibility.offscreen_launch_args() == []
