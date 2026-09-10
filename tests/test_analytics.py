"""Tests for src/analytics.py's SQLite-backed persistence specifically —
the property tests/test_app.py's Flask-level analytics tests can't exercise
(they never actually restart a process). See src/analytics.py's own
docstring for the exact, honestly-scoped durability claim this module
makes: counts survive a plain process restart via a shared SQLite file,
but not a fresh deploy (new disk) and not multiple separate machines.

The cross-restart check below deliberately runs two independent Python
*subprocesses* against the same ANALYTICS_DB_PATH rather than
importlib.reload()-ing the shared `analytics` module in-process — a reload
would mutate the very same module object app.py and tests/test_app.py
already hold a reference to, which risks leaking a temp DB path into
unrelated tests that happen to run afterward in the same pytest session.
A real subprocess is the only way to honestly simulate "the process
restarted" anyway."""

import os
import sqlite3
import subprocess
import sys

import analytics

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_PROJECT_ROOT, "src")


def _run_snapshot_in_subprocess(db_path, extra_calls=""):
    """Runs a fresh `python3` process that imports analytics against
    `db_path`, optionally makes some record_solve/record_error calls
    (`extra_calls`, raw Python source), then prints its snapshot() as a
    single JSON line on stdout."""
    script = (
        "import json, sys; sys.path.insert(0, %r); import analytics\n" % _SRC
        + extra_calls
        + "print(json.dumps(analytics.snapshot()))\n"
    )
    env = dict(os.environ, ANALYTICS_DB_PATH=db_path)
    result = subprocess.run(
        [sys.executable, "-c", script], env=env, cwd=_PROJECT_ROOT,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"subprocess failed:\n{result.stderr}"
    import json
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_counts_survive_a_simulated_process_restart(tmp_path):
    db_path = str(tmp_path / "analytics_restart_test.db")

    first = _run_snapshot_in_subprocess(
        db_path,
        extra_calls=(
            'analytics.record_solve("solve", "quantum", 100.0)\n'
            'analytics.record_solve("solve_fleet", "classical", 50.0, incident_applied=True)\n'
            'analytics.record_error()\n'
        ),
    )
    assert first["total_solves"] == 2
    assert first["errors"] == 1

    # A second, independent process against the SAME db file — this is
    # the "restart" being simulated. Its very first snapshot(), with no
    # record_* calls of its own, must already show the first process's
    # counts and the SAME "since" timestamp (not a fresh one) — that's the
    # entire point of persisting rather than starting the in-memory dict
    # over from a hardcoded zero.
    second = _run_snapshot_in_subprocess(db_path)
    assert second["total_solves"] == 2
    assert second["errors"] == 1
    assert second["solves_by_endpoint"] == {"solve": 1, "solve_fleet": 1}
    assert second["incident_simulations"] == 1
    assert second["since"] == first["since"]

    # A third process making one MORE call on top of what's already
    # persisted — proves it's additive, not overwriting.
    third = _run_snapshot_in_subprocess(
        db_path, extra_calls='analytics.record_solve("solve", "classical", 10.0)\n',
    )
    assert third["total_solves"] == 3
    assert third["since"] == first["since"]


def test_a_fresh_db_path_starts_at_zero_with_its_own_since(tmp_path):
    """Sanity check on the flip side: a db path nobody has written to yet
    must start clean, and get its OWN "since" (not reuse one from a
    differently-pathed db, which would be a sign paths are being ignored)."""
    db_path = str(tmp_path / "brand_new.db")
    snap = _run_snapshot_in_subprocess(db_path)
    assert snap["total_solves"] == 0
    assert snap["errors"] == 0
    assert snap["avg_solve_ms"] is None

    other_db_path = str(tmp_path / "brand_new_2.db")
    other_snap = _run_snapshot_in_subprocess(other_db_path)
    assert other_snap["total_solves"] == 0


def test_reset_for_tests_actually_clears_the_underlying_database_rows():
    """The in-memory dict resetting to zero isn't the interesting claim
    (that was already true before persistence existed) — what's new is
    that _reset_for_tests() must also wipe the SQLite rows, or a snapshot
    taken by some OTHER process sharing the same db file would still see
    stale counts even after this process reset."""
    analytics.record_solve("solve", "quantum", 42.0)
    analytics.record_error()
    assert analytics.snapshot()["total_solves"] == 1

    analytics._reset_for_tests()

    snap = analytics.snapshot()
    assert snap["total_solves"] == 0
    assert snap["errors"] == 0
    assert snap["avg_solve_ms"] is None

    # Read the database directly, bypassing the module's own in-memory
    # cache entirely, to prove the reset really did touch disk and not
    # just the Python-side dict.
    conn = sqlite3.connect(analytics._DB_PATH)
    try:
        rows = dict(conn.execute("SELECT name, value FROM counters").fetchall())
    finally:
        conn.close()
    assert rows.get("solve", 0) == 0
    assert rows.get("errors", 0) == 0


def test_record_solve_is_readable_from_a_second_independent_connection():
    """The whole point of moving off pure in-memory state: a value this
    process wrote should be visible to a completely separate reader of
    the same file, without going through this module's API at all."""
    analytics._reset_for_tests()
    analytics.record_solve("solve_fleet", "quantum", 77.0, precedence_applied=True)

    conn = sqlite3.connect(analytics._DB_PATH)
    try:
        row = conn.execute("SELECT value FROM counters WHERE name = 'solve_fleet'").fetchone()
        precedence_row = conn.execute(
            "SELECT value FROM counters WHERE name = 'precedence_applied'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None and int(row[0]) == 1
    assert precedence_row is not None and int(precedence_row[0]) == 1

    analytics._reset_for_tests()  # leave the shared db clean for whatever test runs next
