#!/usr/bin/env python3
"""Question-by-question comparison of the two historical testbed runs.

Reads the one-per-question run and the three-repeats run, checks that every
question carries identical defining fields in both, and prints each run's
accuracy for the two groups. Standard library only.
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / "testbed" / "runs" / "run-20261015-1559" / "results.csv"
MAIN = ROOT / "testbed" / "runs" / "run-20261015-1607" / "results.csv"

FIELDS = ("kind", "clauses", "state", "action", "intervention", "oracle_answer")
GROUPS = ("normal", "ood")


def load(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def index_questions(rows, label):
    """Map sample_id -> tuple of defining fields, rejecting inconsistent repeats."""
    questions = {}
    for row in rows:
        sample_id = row["sample_id"]
        key = tuple(row[field] for field in FIELDS)
        if sample_id in questions and questions[sample_id] != key:
            raise SystemExit(
                f"{label}: sample_id {sample_id} differs between repeats; "
                "the repeats are not the same question."
            )
        questions[sample_id] = key
    return questions


def accuracy(rows):
    """Return {group: (n, correct)} from the stored per-call outcome."""
    stats = {}
    for row in rows:
        count, correct = stats.get(row["kind"], (0, 0))
        stats[row["kind"]] = (count + 1, correct + int(row["model_correct"]))
    return stats


def main():
    old_rows = load(OLD)
    main_rows = load(MAIN)
    old = index_questions(old_rows, "run-1559")
    main = index_questions(main_rows, "run-1607")

    print("Comparing runs")
    print(f"  old : {OLD.relative_to(ROOT)} ({len(old_rows)} rows, {len(old)} questions)")
    print(f"  main: {MAIN.relative_to(ROOT)} ({len(main_rows)} rows, {len(main)} questions)")
    print(f"  fields compared: {', '.join(FIELDS)}")
    print()

    mismatched = []
    for sample_id in sorted(old, key=int):
        if sample_id not in main:
            mismatched.append((sample_id, "missing from main run"))
        elif old[sample_id] != main[sample_id]:
            differing = [
                field
                for field, a, b in zip(FIELDS, old[sample_id], main[sample_id])
                if a != b
            ]
            mismatched.append((sample_id, "differs in " + ", ".join(differing)))
    for sample_id in sorted(set(main) - set(old), key=int):
        mismatched.append((sample_id, "missing from old run"))

    total = len(old)
    identical = total - len([m for m in mismatched if m[0] in old])
    print(f"Identical questions: {identical}/{total}")
    if mismatched:
        print("Mismatches:")
        for sample_id, reason in mismatched:
            print(f"  sample_id {sample_id}: {reason}")
    print()

    print("Accuracy by group (model_correct)")
    for label, rows in (("run-1559", old_rows), ("run-1607", main_rows)):
        stats = accuracy(rows)
        for group in GROUPS:
            count, correct = stats.get(group, (0, 0))
            percent = 100.0 * correct / count if count else 0.0
            print(f"  {label}  {group:<6}  {correct:>3}/{count:<3} = {percent:5.1f}%")

    if mismatched:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
