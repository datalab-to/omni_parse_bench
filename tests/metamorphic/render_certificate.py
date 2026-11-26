"""Writes CERTIFICATE.md from the registry in common.py and known_deviations.json, or checks it against a run.

    PYTHONPATH=. uv run python tests/metamorphic/render_certificate.py --write  # rewrite CERTIFICATE.md
    PYTHONPATH=. uv run python tests/metamorphic/render_certificate.py          # print it
    PYTHONPATH=. uv run python tests/metamorphic/render_certificate.py --run    # run the tests, compare
"""
from __future__ import annotations

import importlib
import os
import platform
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE.parent)]    # tests/, as pytest puts it: conftest, test_invariants, metamorphic

import conftest  # noqa: E402,F401  (registers the Hypothesis profiles)
import hypothesis  # noqa: E402
import pytest  # noqa: E402
from hypothesis import settings  # noqa: E402

from metamorphic.common import (CHECKS, DATASET_REVISION, DEVIATIONS, HOLDS, MANIFEST_SHA256, POOLS,  # noqa: E402
                               REAL, RELATIONS, RUN_IN_CI, manifest_sha256)

from metamorphic.mutation_check import MUTATIONS  # noqa: E402

COMMAND = "PYTHONPATH=. uv run python tests/metamorphic/render_certificate.py --write"
MODULES = sorted(p.stem for p in HERE.glob("test_*.py") if p.stem != "test_certificate")


def load_every_test_file() -> None:
    """Imports the test files, which fills the registry."""
    for name in MODULES:
        importlib.import_module(f"metamorphic.{name}")


def in_label_order(labels):
    return sorted(labels, key=lambda label: (int(label[1:].rstrip("abcdefg")), label))

# ------------------------------------------------------------------------------------------- render


def case_args(fn) -> list[dict]:
    """The keyword arguments of each test item pytest makes of `fn`, one per combination of its parametrize
    lists."""
    items = [{}]
    for mark in getattr(fn, "pytestmark", []):
        if mark.name == "parametrize":
            names = [n.strip() for n in mark.args[0].split(",")]
            items = [{**kw, **dict(zip(names, v if len(names) > 1 else (v,), strict=True))} for kw in items
                     for v in mark.args[1]]
    return items


def cases(fn) -> int:
    """How many test items pytest makes of `fn`."""
    return len(case_args(fn))


def examples_drawn(fn) -> list[int]:
    """Runs the Hypothesis test `fn` and returns how many examples it drew and passed for each test item
    (its @example cases not counted)."""
    inner, calls, counts = fn.hypothesis.inner_test, [], []
    explicit = len(getattr(fn, "hypothesis_explicit_examples", []))

    def counted(*args, **kwargs):
        inner(*args, **kwargs)
        calls.append(1)

    fn.hypothesis.inner_test = counted
    try:
        for kw in case_args(fn):
            before = len(calls)
            fn(**kw)
            counts.append(len(calls) - before - explicit)
    finally:
        fn.hypothesis.inner_test = inner
    return counts


def evidence(label: str) -> str:
    ci = settings.get_profile("ci").max_examples
    checks = [c for c in CHECKS if label in c["labels"]]
    deviates = RELATIONS[label]["status"] != HOLDS
    counted = [c for c in checks
               if hasattr(c["fn"], "hypothesis") and not (deviates and c["role"] == "relation")]

    def items(c) -> int:    # the test items of `c` that test this label (`case_of` in common.py)
        only = c["case_of"].get(label, {})
        return sum(all(kw.get(k) == v for k, v in only.items()) for kw in case_args(c["fn"]))
    at_most = sum(items(c) * ci for c in counted if c["fn"].__name__ not in RUN_IN_CI)
    ran_out = sum(items(c) * RUN_IN_CI[c["fn"].__name__] for c in counted if c["fn"].__name__ in RUN_IN_CI)
    parts = ["fails on its first example (strict expected failure)"] if deviates else []
    parts += [f"at most {at_most:,} examples"] if at_most else []
    more = " more" if at_most else ""
    parts += [f"{ran_out:,}{more} examples in CI (every input there is)"] if ran_out else []
    for c in checks:
        if c["pool"]:
            desc, fixtures, real = POOLS[c["pool"]]
            parts.append(f"drawn from the loaded {desc} (CI: {fixtures} fixture tests; with the dataset: "
                         f"{real:,})")
        if c["role"] == "relation" and c["note"]:
            parts.append(c["note"])
        elif hasattr(c["fn"], "hypothesis"):
            continue
        elif c["role"] == "more":
            parts.append(f"{cases(c['fn'])} fixed case{'s' * (cases(c['fn']) > 1)}")
        elif c["role"] == "real":
            name, size = REAL[c["over"][label] if isinstance(c["over"], dict) else c["over"]]
            own = len(DEVIATIONS.get(label, {}).get("real_ids", []))
            extra = (f", {own} listed as deviating" if own else f": {c['note']}" if c["note"] else
                     ", none deviates")
            parts.append(f"all {size:,} {name}{extra}")
    if killers := sum(m[0] == label for m in MUTATIONS):
        parts.append(f"fails on each of {killers} mutations of the scorer's rule (mutation_check.py)")
    return "; ".join(dict.fromkeys(parts))


def status(label: str) -> str:
    s = RELATIONS[label]["status"]
    if s == HOLDS:
        return s
    e = DEVIATIONS.get(label, {})
    checked = "yes" if e.get("enumerated_over_real_tests") else "no (see the effect's basis)"
    return "<br>".join([
        f"**{s}**: {e.get('description', 'no entry in known_deviations.json')}",
        f"Example: {e.get('counterexample')}",
        f"Why this label: {e.get('why_this_status')}",
        f"Effect on scores: {e.get('effect_on_scores')} ({e.get('effect_basis')}).",
        f"How common: {e.get('how_common')}. Who is affected: {e.get('who_is_affected')}.",
        f"Enumerated over real tests: {checked}.",
    ])


def render() -> str:
    load_every_test_file()
    rows = []
    for label in in_label_order(RELATIONS):
        fns = [c["fn"] for c in CHECKS if label in c["labels"]]
        tests = ", ".join(f"[`{f.__name__}`]({f.__module__.split('.')[-1]}.py)" for f in fns)
        promise = RELATIONS[label]["promise"]
        rows.append(f"| {label} | {promise} | {status(label)} | {evidence(label)} | {tests} |")
    held = sum(r["status"] == HOLDS for r in RELATIONS.values())
    unpromised = sorted(k for k, e in DEVIATIONS.items() if e.get("promised") is False)
    unpromised_note = ""
    if unpromised:
        unpromised_note = (
            f" ({len(unpromised)} of them, {', '.join(unpromised)}, are about folding a string twice, "
            "which the scorer never does and no document promises, so they change no score)")
    return "\n".join([
        "# Certificate of the scorer's relations",
        "",
        f"Generated by `{COMMAND}`; do not edit by hand. How to read it: [README.md](README.md).",
        "",
        f"A register of {len(RELATIONS)} relations its authors selected, not every relation of the scorer "
        f"(see 'Not covered' in the README): {held} hold, {len(RELATIONS) - held} deviate{unpromised_note}. "
        "HOLDS means no "
        "counterexample in the sampled examples, nor, when OPB_DATASET is set, in the checks over every real "
        f"test of the published dataset at revision {DATASET_REVISION[:7]}. It is not a proof.",
        "",
        f"- Each Hypothesis test tries at most {settings.get_profile('ci').max_examples} examples in CI "
        f"({settings.get_profile('deep').max_examples:,} in the deep profile, which CI does not run). It "
        "tries fewer when its input space runs out; the evidence column then gives the count.",
        "- CI does not set OPB_DATASET, so it skips every check over real tests. The real-test counts below "
        "are constants in the source, from runs with the dataset set, and are checked only when it is set.",
        "- `--run` reports a row as passed from the checks it ran, and says how many it skipped.",
        "- Effects on scores marked 'Measured on cached leaderboard re-runs' cannot "
        "be re-run from this package.",
        "- A deviation whose effect is 'unknown' is one that could change a score: treat it as open.",
        "- A relation that says it 'fails on each of N mutations' was run against N copies of the scorer, "
        "each with the rule it pins removed or changed, and failed on every one (`mutation_check.py`; CI "
        "does not run it).",
        "- M104 to M120 are taken from the perturbation catalogue of ParseBench-2 (arXiv 2611.17400, "
        "Appendix A.2, "
        "CC BY 4.0), written as relations from this scorer's documented rules.",
        "",
        "| label | promise | status | evidence | tests |",
        "|---|---|---|---|---|",
        *rows,
        "",
    ])

# --------------------------------------------------------------------------------------------- run


def outcomes(junit: Path) -> dict[str, list[str]]:
    """Each test function's outcomes in a pytest junit report: passed, expected failure, FAILED or skipped."""
    got: dict[str, list[str]] = {}
    for case in ET.parse(junit).iter("testcase"):
        tags = {child.tag: child for child in case}
        if "failure" in tags or "error" in tags:
            result = "FAILED"
        elif "skipped" in tags:
            result = "expected failure" if tags["skipped"].get("type") == "pytest.xfail" else "skipped"
        else:
            result = "passed"
        got.setdefault(case.get("name").split("[")[0], []).append(result)
    return got


def compare(junit: Path) -> tuple[list[tuple[str, str, str, bool]], bool]:
    """One row per relation (label, certificate status, result in this run, whether they agree), and the
    certificate's own checks; and whether everything agrees."""
    load_every_test_file()
    got, rows = outcomes(junit), []
    for label in in_label_order(RELATIONS):
        r = RELATIONS[label]
        want = "passed" if r["status"] == HOLDS else "expected failure"
        main = got.get(r["fn"].__name__, [])
        others = [o for c in CHECKS if label in c["labels"] and c["fn"] is not r["fn"]
                  for o in got.get(c["fn"].__name__, [])]
        result = ("not run" if not main else "FAILED" if "FAILED" in main + others else
                  want if set(main) == {want} else " / ".join(sorted(set(main))))
        skipped = others.count("skipped")
        note = f" ({skipped} other check{'s' * (skipped > 1)} skipped)" if skipped and result == want else ""
        rows.append((label, r["status"], result + note, result == want))
    own = [o for name in CERTIFICATE_TESTS for o in got.get(name, [])]
    fine = "FAILED" not in own
    rows.append(("certificate checks", "passed", "passed" if fine else "FAILED", fine))
    return rows, all(row[3] for row in rows)


CERTIFICATE_TESTS = ("test_the_certificate_is_current", "test_each_status_matches_the_tests_xfail_marker",
                     "test_every_test_is_registered_and_says_why_it_matters",
                     "test_the_certificate_counts_the_real_tests_it_says",
                     "test_the_certificate_pools_are_the_loaded_tests",
                     "test_the_certificate_counts_the_examples_it_says_ran_in_ci",
                     "test_every_deviation_cites_files_that_exist",
                     "test_the_run_report_flags_a_mismatch")


def dataset_revision() -> tuple[str, bool]:
    """What `--run` says of the dataset, and whether it is the certified revision (or none is set). Only the
    manifest file is hashed: it pins the list of pages, not the gold files."""
    if not os.environ.get("OPB_DATASET"):
        return "dataset none", True
    folder = Path(os.environ["OPB_DATASET"])
    try:
        same = manifest_sha256(folder) == MANIFEST_SHA256
    except OSError:
        return f"dataset folder {folder.name}: no manifest", False
    said = f"manifest is revision {DATASET_REVISION[:7]}'s" if same else \
        f"manifest is NOT revision {DATASET_REVISION[:7]}'s (sha256 differs)"
    return f"dataset folder {folder.name}, {said}", same


def header() -> str:
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return (f"scorer {git('describe', '--tags', '--always', '--dirty') or 'unknown'} (commit "
            f"{git('rev-parse', 'HEAD') or 'unknown'}); python "
            f"{platform.python_version()}; pytest {pytest.__version__}; hypothesis {hypothesis.__version__}; "
            f"{dataset_revision()[0]}; profile {os.environ.get('HYPOTHESIS_PROFILE', 'ci')}")


def run() -> int:
    """Runs the package under pytest, prints each relation's status beside its result, and returns 1 on any
    mismatch."""
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "junit.xml"
        path = os.pathsep.join(filter(None, [str(ROOT), os.environ.get("PYTHONPATH")]))
        env = {**os.environ, "PYTHONPATH": path}
        subprocess.run([sys.executable, "-m", "pytest", str(HERE), "-q", "-p", "no:cacheprovider",
                        f"--junitxml={junit}"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL)
        rows, ok = compare(junit)
    print(header())
    print(f"{'relation':<20} {'certificate status':<34} result in this run")
    for label, want, result, agrees in rows:
        print(f"{label:<20} {want:<34} {result}{'' if agrees else '   <-- MISMATCH'}")
    print("every status matches this run" if ok else f"{sum(not r[3] for r in rows)} mismatches")
    if not dataset_revision()[1]:
        print(f"the dataset is not revision {DATASET_REVISION[:7]}: the real-test counts do not apply to it")
    return 0 if ok and dataset_revision()[1] else 1


if __name__ == "__main__":
    if "--run" in sys.argv:
        sys.exit(run())
    text = render()
    if "--write" in sys.argv:
        (HERE / "CERTIFICATE.md").write_text(text)
    else:
        print(text, end="")
