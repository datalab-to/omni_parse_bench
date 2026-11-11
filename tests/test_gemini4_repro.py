"""Offline checks for the paid runner's selection and confirmation boundaries."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("mode", ["plan", "denied", "retry", "no-failures"])
def test_staged_reproducer_preserves_successes_and_keeps_all_retry_outcomes(tmp_path, monkeypatch, mode):
    script = Path(__file__).resolve().parents[1] / "scripts/reproduce_gemini4.py"
    spec = importlib.util.spec_from_file_location("gemini4_repro", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Model execution is replaced entirely. The actual reader is still loaded on the retry path.
    monkeypatch.setattr(module.llm, "__file__", str(tmp_path / "installed/llm.py"))
    monkeypatch.setattr(module.llm, "as_blocks", lambda text: None)
    monkeypatch.setattr(module.harness, "system", lambda model, options: model)
    original = [{"id": "successful", "status": "ok", "score": 1},
                {"id": "failed", "status": "failed", "score": 0}]
    if mode == "no-failures":
        original = original[:1]
    retry_line = {"id": "failed", "status": "failed", "score": 0, "retry": True}
    plans, predictions, summaries = [], [], []

    class Scorer:
        def summarize(self, combined):
            summaries.append(combined)
            return {"combined": combined}

        def _framed(self, summary, combined, name):
            return summary

    class Benchmark:
        def plan(self, system, folder, **options):
            run = SimpleNamespace(folder=folder, name=f"run-{len(plans)}")
            plan = SimpleNamespace(run=run, rows=original)
            plans.append(options)
            return plan

        def predict(self, plan):
            predictions.append(plan)
            score_file = plan.run.folder / "unit_tests/scores.jsonl"
            score_file.parent.mkdir(parents=True)
            rows = original if len(predictions) == 1 else [retry_line]
            score_file.write_text("\n".join(json.dumps(row) for row in rows))

        def grade(self, run):
            return {"scorers": {"unit_tests": {"initial": True}}}

    monkeypatch.setattr(module, "UnitTests", Scorer)
    monkeypatch.setattr(module.benchmark, "Benchmark", lambda *args: Benchmark())
    args = [str(script), "google/gemini-4-argon", "--out", str(tmp_path / "runs")]
    args += ["--plan"] if mode == "plan" else ([] if mode == "denied" else ["--yes"])
    monkeypatch.setattr(sys, "argv", args)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    module.main()
    assert plans[0]["sample"] == 5
    if mode in {"plan", "denied"}:
        assert not predictions
        assert not list(tmp_path.rglob("*-summary.json"))
        return
    result = json.loads(next(tmp_path.rglob("*-summary.json")).read_text())
    if mode == "no-failures":
        assert len(predictions) == 1
        assert result["failed_page_rerun"] is None
    else:
        assert len(predictions) == 2
        assert plans[1]["only"] == ["failed"]
        assert summaries == [[original[0], retry_line]]
        assert result["full_summary"]["combined"] == [original[0], retry_line]
