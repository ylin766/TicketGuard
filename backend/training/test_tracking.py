"""Tests for iteration tracking and plotting. Offline: local JSONL run log only,
Phoenix mirror disabled; plots render to a tmp dir with the Agg backend."""

from backend.training.plots import plot_run
from backend.training.tracking import IterationRecord, load_run, log_iteration


def test_log_and_load_roundtrip(tmp_path):
    rec = IterationRecord(
        run_name="t", iteration=0, split_name="test",
        accuracy=0.7, mean_score=0.65, mean_tool_success=0.9, n=10,
    )
    log_iteration(rec, runlog_dir=tmp_path, mirror_to_phoenix=False)
    loaded = load_run("t", runlog_dir=tmp_path)
    assert len(loaded) == 1
    assert loaded[0].accuracy == 0.7
    assert loaded[0].split_name == "test"


def test_log_appends(tmp_path):
    for i in range(3):
        log_iteration(
            IterationRecord(run_name="t", iteration=i, split_name="test", accuracy=0.5 + i * 0.1),
            runlog_dir=tmp_path, mirror_to_phoenix=False,
        )
    loaded = load_run("t", runlog_dir=tmp_path)
    assert [r.iteration for r in loaded] == [0, 1, 2]
    assert [r.accuracy for r in loaded] == [0.5, 0.6, 0.7]


def test_load_missing_run_is_empty(tmp_path):
    assert load_run("does-not-exist", runlog_dir=tmp_path) == []


def test_plot_run_produces_pngs(tmp_path, monkeypatch):
    # Write a run log into a tmp runs dir, then point plotting at it.
    from backend.training import tracking

    runs_dir = tmp_path / "runs"
    for i in range(4):
        log_iteration(
            IterationRecord(
                run_name="curve", iteration=i, split_name="test",
                accuracy=0.6 + i * 0.08, mean_tool_success=0.7 + i * 0.05, n=10,
            ),
            runlog_dir=runs_dir, mirror_to_phoenix=False,
        )
    # plot_run reads via load_run(default dir); redirect default to our tmp.
    monkeypatch.setattr(tracking, "DEFAULT_RUNLOG_DIR", runs_dir)
    plots_dir = tmp_path / "plots"
    saved = plot_run("curve", plot_dir=plots_dir)
    assert len(saved) == 3
    for p in saved:
        assert p.exists() and p.stat().st_size > 0


def test_plot_run_empty_returns_nothing(tmp_path, monkeypatch):
    from backend.training import tracking

    monkeypatch.setattr(tracking, "DEFAULT_RUNLOG_DIR", tmp_path / "runs")
    assert plot_run("nope", plot_dir=tmp_path / "plots") == []
