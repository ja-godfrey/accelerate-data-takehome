#!/usr/bin/env python3
"""
Public conformance checks for the Accelerate data-engineering take-home.

Runs your pipeline, verifies the OUTPUTS conform to the contract in
output_spec.md, runs it a second time to confirm idempotency, and prints
"N/6 checks passed". This is exactly what CI runs on every push.

IMPORTANT: these six checks confirm your output matches the *shape* of the
contract you were given (files, columns, sorting, pseudonymization, well-formed
quarantine/findings, idempotent re-runs). They do NOT check whether your
numbers are correct, and they do not tell you what is wrong with the data --
finding that is the exercise. Correctness, runtime, and edge-case handling are
scored after you submit, on a dataset you have not seen. Passing all six is
necessary, not sufficient. See README.md.

Runs `python pipeline.py` (your entry point at the repo root).

Usage:
  python checks/public_checks.py                 # auto: full/ if present, else sample/
  python checks/public_checks.py --data sample   # force the small in-repo dataset
  python checks/public_checks.py --no-run        # only validate an existing outputs/

Exit status is zero only at 6/6, so a green CI run means the complete public
conformance gate passed. Partial Bronze progress is still printed and summarized.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SCHEMAS = {
    "sessions.csv": ["source_system", "session_id", "start_scheduled", "start_actual",
                     "length_minutes", "location", "status", "district", "program",
                     "tutor_pseudo_id", "n_enrolled", "n_present", "n_absent", "subject"],
    "attendance.csv": ["source_system", "session_id", "student_pseudo_id", "attended",
                       "status_normalized", "joined_at", "left_at", "minutes_attended",
                       "grade", "canonical_school_id"],
    "program_summary.csv": ["month", "district", "canonical_school_id",
                            "canonical_school_name", "sessions_completed", "sessions_missed",
                            "attendance_rate", "unique_students", "tutoring_minutes"],
    "tutor_conflicts.csv": ["source_system", "tutor_pseudo_id", "session_id_1",
                            "session_id_2", "overlap_minutes"],
    "dq_findings.csv": ["rule_id", "severity", "source_system", "record_ref", "note"],
}
SORT_KEYS = {
    "sessions.csv": [0, 1],
    "attendance.csv": [0, 1, 2],
    "program_summary.csv": [0, 1, 2],
    "tutor_conflicts.csv": [0, 1, 2, 3],
}
UNIQUE_KEYS = {
    "sessions.csv": [0, 1],
    "attendance.csv": [0, 1, 2],
    "program_summary.csv": [0, 1, 2],
    "tutor_conflicts.csv": [0, 1, 2, 3],
}
REASONS = {"EMPTY_FILE", "MALFORMED_FILE", "UNKNOWN_FEED", "UNPARSEABLE_ROW",
           "CONFLICTING_RECORDS", "OTHER"}
SEVERITIES = {"INFO", "WARN", "ERROR"}
QUAR_HEADER = ["source_system", "record_ref", "reason_code", "detail"]
PSEUDO_COLS = {
    "sessions.csv": [(9, "tutor")],
    "attendance.csv": [(2, "student")],
    "tutor_conflicts.csv": [(1, "tutor")],
}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
HEX16_RE = re.compile(r"^[0-9a-f]{16}$")
IDENT_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@+-]*")
TIMEOUT_S = 2400
OUT_FILES = list(SCHEMAS)


def read_csv(path):
    if not os.path.exists(path):
        return None, None
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        r = csv.reader(f)
        return next(r, []), list(r)


def tracked_paths(outdir, qdir):
    paths = []
    if os.path.isdir(outdir):
        for root, _, files in os.walk(outdir):
            for name in files:
                path = os.path.join(root, name)
                rel = os.path.relpath(path, outdir).replace("\\", "/")
                paths.append((f"outputs/{rel}", path))
    for name in OUT_FILES:
        path = os.path.join(outdir, name)
        if not any(existing == path for _, existing in paths):
            paths.append((f"outputs/{name}", path))
    if os.path.isdir(qdir):
        for root, _, files in os.walk(qdir):
            for name in files:
                path = os.path.join(root, name)
                rel = os.path.relpath(path, qdir).replace("\\", "/")
                paths.append((f"quarantine/{rel}", path))
    qcsv = os.path.join(qdir, "quarantined_rows.csv")
    if not any(path == qcsv for _, path in paths):
        paths.append(("quarantine/quarantined_rows.csv", qcsv))
    return paths


def hash_tree(paths):
    h = hashlib.sha256()
    for label, p in sorted(paths):
        h.update(label.encode())
        if os.path.exists(p):
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
    return h.hexdigest()


def collect_raw_identifiers(landing_dir):
    """Collect source student/tutor ids so checks can verify the actual salted hash
    and detect raw UUID-like identifiers copied into findings."""
    known_vendors = ("northquill", "quadrant", "summitsteps", "cognivo")
    found = {v: {"student": set(), "tutor": set()} for v in known_vendors}
    found["_unknown"] = {"student": set(), "tutor": set()}
    def normalized(value):
        value = str(value or "").replace("\u00a0", " ")
        for char in ("\u200b", "\u200c", "\u200d", "\ufeff"):
            value = value.replace(char, "")
        return " ".join(value.split())
    layouts = {
        "northquill": ("utf-8", ",", ("student_id",), ("tutor_id",)),
        "quadrant": ("cp1252", ",", ("StudentGUID",), ("TutorGUID",)),
        "summitsteps": ("utf-8", "|", ("student_uid",), ("tutor_uid",)),
    }
    if not os.path.isdir(landing_dir):
        return found
    for root, _, files in os.walk(landing_dir):
        for name in files:
            lower = name.lower()
            path = os.path.join(root, name)
            vendor = next((v for v in known_vendors if lower.startswith(v + "_")), None)
            if not vendor:
                if lower.endswith(".csv"):
                    try:
                        with open(path, newline="", encoding="utf-8", errors="replace") as f:
                            for row in csv.DictReader(f):
                                for column, value in row.items():
                                    key = str(column or "").lower()
                                    kind = ("student" if "student" in key else
                                            "tutor" if "tutor" in key else None)
                                    value = normalized(value)
                                    if kind and value:
                                        found["_unknown"][kind].add(value)
                    except (OSError, csv.Error):
                        pass
                continue
            if vendor == "cognivo":
                try:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        for line in f:
                            try:
                                obj = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            student = normalized(obj.get("participant", {}).get("id", ""))
                            tutor = normalized(obj.get("facilitator", {}).get("id", ""))
                            if student:
                                found[vendor]["student"].add(student)
                            if tutor:
                                found[vendor]["tutor"].add(tutor)
                except OSError:
                    continue
                continue
            encoding, delim, student_cols, tutor_cols = layouts[vendor]
            try:
                with open(path, newline="", encoding=encoding, errors="replace") as f:
                    for row in csv.DictReader(f, delimiter=delim):
                        for kind, columns in (("student", student_cols), ("tutor", tutor_cols)):
                            value = next((row.get(c) for c in columns if row.get(c)), "")
                            value = normalized(value)
                            if value and value not in columns:
                                found[vendor][kind].add(value)
            except (OSError, csv.Error):
                continue
    return found


def pii_leaks(outdir, data, raw_ids, salt):
    leaks = []
    expected_paths = {os.path.abspath(os.path.join(outdir, name)) for name in OUT_FILES}
    if os.path.isdir(outdir):
        unexpected = [os.path.relpath(os.path.join(root, name), outdir)
                      for root, _, files in os.walk(outdir) for name in files
                      if os.path.abspath(os.path.join(root, name)) not in expected_paths]
        if unexpected:
            leaks.append(f"unexpected file in OUTPUT_DIR: {unexpected[0]}")
    valid = {vendor: {
        kind: {hashlib.sha256(f"{salt}|{vendor}|{raw}".encode()).hexdigest()[:16]
               for raw in values}
        for kind, values in kinds.items()}
        for vendor, kinds in raw_ids.items()}
    sensitive_tokens = {
        raw for kinds in raw_ids.values() for values in kinds.values() for raw in values
        if len(raw) >= 8 and not raw.isdigit()
    }
    for fname in OUT_FILES:
        if fname not in data:
            continue
        for row in data[fname][1]:
            if any("@" in value and EMAIL_RE.search(value) for value in row):
                leaks.append(f"{fname}: email address in output")
                break
        if leaks:
            break
    if not leaks:
        for fname, cols in PSEUDO_COLS.items():
            if fname not in data or data[fname][0] != SCHEMAS[fname]:
                continue
            for row in data[fname][1]:
                vendor = row[0] if row else ""
                for col, kind in cols:
                    value = row[col] if len(row) > col else ""
                    if value and (not HEX16_RE.match(value) or
                                  value not in valid.get(vendor, {}).get(kind, set())):
                        leaks.append(
                            f"{fname}: id is not the expected salted {kind} pseudonym")
                        break
                if leaks:
                    break
            if leaks:
                break
    if not leaks:
        for fname, (_, rows) in data.items():
            for row in rows:
                for value in row:
                    exposed = sensitive_tokens.intersection(IDENT_TOKEN_RE.findall(value))
                    if exposed:
                        leaks.append(f"{fname}: raw student/tutor identifier in output")
                        break
                if leaks:
                    break
            if leaks:
                break
    if not leaks and "dq_findings.csv" in data:
        # A vendor finding may use vendor:session[:student_pseudo_id]. Validate
        # the optional identifier structurally as well as scanning long raw
        # tokens above; this also catches short numeric source ids that would be
        # too ambiguous to ban from every free-text output field.
        for row in data["dq_findings.csv"][1]:
            if len(row) < 4:
                continue
            parts = row[3].split(":")
            vendor = parts[0]
            if vendor in valid and len(parts) >= 3:
                value = parts[-1]
                if value not in valid[vendor]["student"]:
                    leaks.append(
                        "dq_findings.csv: record_ref does not contain the expected "
                        "salted student pseudonym")
                    break
    return leaks


def run_pipeline(cmd, env, timeout, cwd):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, shell=isinstance(cmd, str), env=env, timeout=timeout,
                           cwd=cwd, capture_output=True, text=True, errors="replace")
    except subprocess.TimeoutExpired:
        return None, time.time() - t0, "TIMEOUT"
    return p.returncode, time.time() - t0, (p.stderr or "")[-2000:]


def evaluate(outdir, qdir, ran_ok, idempotent, idem_detail, raw_ids=None, salt=None):
    """Return a list of (name, ok, detail) for the six conformance checks."""
    checks = []
    qfile = os.path.join(qdir, "quarantined_rows.csv")

    # 1. all outputs present (implies the pipeline ran and wrote them)
    present = {f: os.path.exists(os.path.join(outdir, f)) for f in OUT_FILES}
    q_present = os.path.exists(qfile)
    missing = [f for f, ok in present.items() if not ok] + \
              ([] if q_present else ["quarantine/quarantined_rows.csv"])
    checks.append(("outputs_present", ran_ok and not missing,
                   "all present" if not missing else f"missing: {missing}"))

    data = {f: read_csv(os.path.join(outdir, f)) for f in OUT_FILES if present[f]}

    # 2. columns match the spec exactly
    wrong = [f for f in OUT_FILES if present[f] and data[f][0] != SCHEMAS[f]]
    cdetail = "outputs missing" if missing else (f"wrong header: {wrong}" if wrong else "exact")
    checks.append(("columns_match", not missing and not wrong, cdetail))

    # 3. rows sorted by the required keys, and natural keys unique
    problems = []
    for f, keys in SORT_KEYS.items():
        if not present[f] or data[f][0] != SCHEMAS[f]:
            problems.append(f"{f}: unreadable")
            continue
        bad_width = sum(1 for row in data[f][1] if len(row) != len(SCHEMAS[f]))
        if bad_width:
            problems.append(f"{f}: {bad_width} row(s) have the wrong field count")
            continue
        keyed = [tuple(r[i] for i in keys) for r in data[f][1]]
        if keyed != sorted(keyed):
            problems.append(f"{f}: not sorted")
    for f, keys in UNIQUE_KEYS.items():
        if present[f] and data[f][0] == SCHEMAS[f]:
            keyed = [tuple(r[i] for i in keys) for r in data[f][1]]
            if len(keyed) != len(set(keyed)):
                problems.append(f"{f}: {len(keyed) - len(set(keyed))} duplicate keys")
    checks.append(("sorted_and_unique", not problems, "; ".join(problems) or "ok"))

    # 4. ids use the requested salt, and no raw identifier/email appears in outputs
    leaks = (pii_leaks(outdir, data, raw_ids, salt) if raw_ids is not None and salt
             else [])
    pii_detail = "outputs missing" if missing else ("; ".join(leaks)[:160] or "clean")
    checks.append(("pseudonymized_no_pii", not missing and not leaks, pii_detail))

    # 5. quarantine + findings files well-formed (format only; no answer key)
    notes = []
    qh, qrows = read_csv(qfile)
    if qh != QUAR_HEADER:
        notes.append("quarantine header wrong")
    elif any(len(r) != 4 for r in qrows):
        notes.append("quarantine rows not 4 fields")
    else:
        codes = {r[2] for r in qrows}
        if not codes <= REASONS:
            notes.append(f"invalid reason codes: {sorted(codes - REASONS)[:4]}")
    fh, frows = data.get("dq_findings.csv", (None, None))
    if fh != SCHEMAS["dq_findings.csv"]:
        notes.append("findings header wrong")
    elif not frows:
        notes.append("findings file empty")
    elif any(len(r) != 5 or r[1] not in SEVERITIES for r in frows):
        notes.append("findings rows malformed")
    checks.append(("quarantine_findings_wellformed", not notes, "; ".join(notes) or "ok"))

    # 6. pipeline re-runs byte-identically
    checks.append(("idempotent_rerun", bool(idempotent), idem_detail))
    return checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", choices=["auto", "sample", "full"], default="auto")
    ap.add_argument("--cmd", default=None, help="pipeline command (default: python pipeline.py)")
    ap.add_argument("--no-run", action="store_true")
    ap.add_argument("--root", default=ROOT, help="repo root containing pipeline.py")
    ap.add_argument("--dataroot", default=None, help="dataset dir with landing/ and reference/")
    ap.add_argument("--outputs", default=None)
    ap.add_argument("--quarantine", default=None)
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--salt", default="public-check-salt")
    ap.add_argument("--timeout", type=int, default=TIMEOUT_S)
    a = ap.parse_args()

    root = os.path.abspath(a.root)
    # Resolve CLI paths before changing the candidate process's working
    # directory. Relative overrides should remain relative to where the
    # checker was invoked, not to the candidate repository.
    outputs = os.path.abspath(a.outputs) if a.outputs else os.path.join(root, "outputs")
    quarantine = (os.path.abspath(a.quarantine) if a.quarantine
                  else os.path.join(root, "quarantine"))
    scale = a.data
    if scale == "auto":
        scale = "full" if os.path.isdir(os.path.join(root, "full", "landing")) else "sample"
    dataroot = (os.path.abspath(a.dataroot) if a.dataroot
                else os.path.join(root, scale))

    ran_ok, idempotent, idem_detail = True, False, "not attempted"
    if not a.no_run:
        cmd = a.cmd
        if not cmd:
            if not os.path.exists(os.path.join(root, "pipeline.py")):
                sys.exit("No pipeline.py at the repo root (and no --cmd given). See README.md.")
            cmd = [sys.executable, "pipeline.py"]
        env = dict(os.environ,
                   LANDING_DIR=os.path.join(dataroot, "landing"),
                   REFERENCE_DIR=os.path.join(dataroot, "reference"),
                   OUTPUT_DIR=outputs, QUARANTINE_DIR=quarantine, PSEUDONYM_SALT=a.salt)
        for d in (outputs, quarantine):
            shutil.rmtree(d, ignore_errors=True)
        print(f"== run 1 ({scale} data) ==")
        rc, t1, err = run_pipeline(cmd, env, a.timeout, root)
        ran_ok = rc == 0
        if not ran_ok:
            print(f"pipeline exited {rc} after {t1:.0f}s. stderr tail:\n{err}")
        else:
            print(f"   completed in {t1:.0f}s")
            h1 = hash_tree(tracked_paths(outputs, quarantine))
            print("== run 2 (idempotency) ==")
            rc2, t2, _ = run_pipeline(cmd, env, a.timeout, root)
            if rc2 != 0:
                idem_detail = "second run failed"
            elif hash_tree(tracked_paths(outputs, quarantine)) == h1:
                idempotent, idem_detail = True, "byte-identical"
            else:
                idem_detail = "outputs changed between identical runs"
    else:
        idem_detail = "not checked (--no-run)"

    raw_ids = collect_raw_identifiers(os.path.join(dataroot, "landing"))
    checks = evaluate(outputs, quarantine, ran_ok, idempotent, idem_detail,
                      raw_ids=raw_ids, salt=a.salt)
    passed = sum(1 for _, ok, _ in checks if ok)
    by = {n: ok for n, ok, _ in checks}
    tier = "silver" if passed == len(checks) else (
        "bronze" if by["outputs_present"] and by["columns_match"] else "-")

    print()
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:28} {detail}")
    print(f"\nPUBLIC CHECKS: {passed}/{len(checks)} passed   conformance tier: {tier}")
    print("These confirm your output fits the contract - not that it is correct.")
    print("Correctness, runtime, and edge cases are scored on the hidden set after you submit.")

    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as f:
            json.dump({"passed": passed, "of": len(checks), "tier": tier,
                       "checks": [{"name": n, "ok": ok, "detail": d}
                                  for n, ok, d in checks]}, f, indent=2)
    # A green CI check means the full public conformance gate passed. Partial
    # Bronze progress remains visible in the summary but correctly stays red.
    sys.exit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
