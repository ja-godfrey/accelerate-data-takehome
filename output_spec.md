# Output Specification (the contract)

Your pipeline reads a landing zone of vendor drop files plus reference data and
produces the standardized outputs below. Automated checks compare your outputs
against this contract — follow it exactly, including column names, order,
sorting, and formatting. Where the spec leaves something unstated, make a
reasonable call and record it in your submission notes.

## 1. Run contract

- Entry point: **`pipeline.py`** at the repo root, run as `python pipeline.py`.
  CI, the self-check, and the reviewers all invoke exactly that.
- That one run processes **everything currently present** in the landing zone,
  end to end. A full rebuild on every run is fine at this volume.
- **Determinism / idempotency:** running twice on the same inputs must produce
  byte-identical outputs. The checker verifies this.
- **Scale:** the full dataset is ~1M rows across the drops, and runtime is
  measured when we score you. Mind the algorithmic complexity of cross-row work
  — the tutor-conflict report especially — where the naive shape can be orders
  of magnitude slower than a good one.
- Environment variables (your pipeline must honor all five):

| Variable | Meaning | Default you may assume |
|---|---|---|
| `LANDING_DIR` | root of the drop folders (`<YYYY-MM>/...`) | `full/landing`, else `sample/landing` |
| `REFERENCE_DIR` | contains `school_crosswalk.csv` | `full/reference`, else `sample/reference` |
| `OUTPUT_DIR` | where the five output files go | `outputs` |
| `QUARANTINE_DIR` | quarantined files + rows | `quarantine` |
| `PSEUDONYM_SALT` | secret salt for pseudonymization | none — **fail loudly if unset** |

Hidden correctness and safety are graded on a compact, incident-complete set;
a separate ~1.8M-line run is used only for 5 runtime points. The scoring
container provides 2 CPUs, 8 GiB RAM, 2 GiB writable `/tmp`, a 10-minute
compact-run limit, and a 40-minute full-scale limit.

`OUTPUT_DIR` and `QUARANTINE_DIR` are pipeline-owned children of a writable
runtime area. A full rebuild may remove and recreate either directory. The
scorer preserves their parent mount so this behaves like the supplied local
checker; do not assume ownership of either directory's parent.

## 2. Text normalization (applies to every text field before any matching, grouping, or output)

1. Trim leading/trailing whitespace; collapse internal whitespace runs to one space.
2. Remove zero-width characters (U+200B, U+200C, U+200D, U+FEFF).
3. Convert non-breaking spaces (U+00A0) to regular spaces.

Vendor systems occasionally emit non-printing characters; they must not create
distinct entities in your outputs.

## 3. File handling

- Feeds are recognized by filename prefix: `northquill_`, `quadrant_`,
  `summitsteps_`, `cognivo_` (see `vendor_feeds.md`).
- Files named `school_crosswalk*.csv` anywhere in the landing zone are
  **reference data**, not session feeds: when multiple versions exist
  (`school_crosswalk.csv`, `..._v2.csv`, ...), the **highest version applies to
  the entire rebuild**.
- Quarantine an entire file (never partially ingest it) when:
  - the filename prefix is not a known feed → reason `UNKNOWN_FEED`;
  - it is zero bytes → `EMPTY_FILE`;
  - it cannot be decoded, or its final line is incomplete (missing trailing
    newline — a truncated transfer) → `MALFORMED_FILE`.
- Quarantine a single row → `UNPARSEABLE_ROW` when it has the wrong field
  count, echoes the header (a concatenated export), or is missing/failing on
  key fields (`session id`, `student id`, parseable start time, length).
- A quarantined file or row must not contribute to any output. The run must
  continue past quarantined inputs.

## 4. Record resolution (dedup and corrections)

- Natural key: **(source_system, session_id, student_id)** — one output row per key.
- Vendors re-send files and corrections. Among records sharing a key, keep the
  one with the **greatest `exported_at`**.
- Records identical on every field collapse silently.
- Records that share the greatest `exported_at` but differ on any field are
  unresolvable: quarantine **all** records for that key → `CONFLICTING_RECORDS`,
  exclude the key from outputs, and log a finding.
- Session-level values (times, status, length, district, program, tutor) come
  from the surviving record with the greatest `(exported_at, student_id)`.

## 5. Field derivations

- **source_system** in reporting rows → lowercase provider key: `northquill`,
  `quadrant`, `summitsteps`, or `cognivo`. Findings/quarantine rows use that
  key when the provider is known and may leave it blank for an unknown feed.
- **Timestamps** → `YYYY-MM-DD HH:MM:SS`. Feeds use several input formats
  (see `vendor_feeds.md`); parse them all.
- **grade** → zero-padded `01`–`12`; anything else (blank, junk, `N/A`) → `UNKNOWN`.
- **location** → uppercase (`ONLINE`, `IN PERSON`).
- **status** → `COMPLETED` or `MISSED`; feeds without a session-status field
  (Cognivo) are all `COMPLETED`.
- **subject** → uppercase; feeds without a subject field → `MATH`.
- **attended** → `1`/`0` from the feed's attendance flag; participants listed
  by Cognivo all attended.
- **minutes_attended** → the provider's minutes value if
  `0 < value <= length_minutes`, formatted with one decimal (`27.0`);
  otherwise blank. Do not recompute from join/leave times.
- **n_present** → recompute as the count of surviving attendance rows with
  `attended = 1` (provider headcounts are not trusted).
- **n_absent** → `n_enrolled - n_present` when the feed supplies enrollment and
  the result is >= 0; otherwise blank (log a finding when negative).
- **month** → first 7 chars of `start_scheduled`.
- **Integer measures** → base-10 digits with no decimal point or thousands
  separators. This applies to `length_minutes`, nonblank enrollment/headcount
  fields, session/student counts, `tutoring_minutes`, and `overlap_minutes`.
- **School resolution** → look up (source_system, normalized school ref) in the
  crosswalk. Identical duplicate crosswalk rows collapse; **conflicting**
  mappings for one ref → treat as unmapped and log `CONFLICTING_XWALK`;
  refs not in the crosswalk → `canonical_school_id = UNMAPPED`,
  `canonical_school_name = UNMAPPED`, log `UNMAPPED_SCHOOL` once per ref.
  School and grade are **row-level** attributes (they live on attendance rows).

## 6. Pseudonymization (FERPA)

- `pseudo_id = sha256("{SALT}|{source_system}|{raw_id}")` hex, first 16 chars,
  with `SALT` from `PSEUDONYM_SALT`. Apply to student ids and tutor ids.
- Raw student/tutor identifiers and tutor emails must not appear anywhere in
  `OUTPUT_DIR` — including `record_ref` and free text copied into findings.
  When a finding refers to a student, use that student's `student_pseudo_id`.
- `QUARANTINE_DIR` is a restricted zone: raw values are permitted there so
  issues can be investigated.

## 7. Output files (exact columns, exact order)

`OUTPUT_DIR` must contain only the five files below. Write diagnostic logs to
stdout/stderr and keep raw investigative material in `QUARANTINE_DIR`.

**`sessions.csv`** — one row per (source_system, session_id); sort by both.
`source_system, session_id, start_scheduled, start_actual, length_minutes,
location, status, district, program, tutor_pseudo_id, n_enrolled, n_present,
n_absent, subject`

**`attendance.csv`** — one row per natural key; sort by
(source_system, session_id, student_pseudo_id).
`source_system, session_id, student_pseudo_id, attended, status_normalized,
joined_at, left_at, minutes_attended, grade, canonical_school_id`
(`status_normalized`: `ATTENDED` / `ABSENT`.)

**`program_summary.csv`** — one row per (month, district, canonical_school_id);
sort by all three. Group **attendance rows** by month of the session's
`start_scheduled`, the session's district, and the row's school.
`month, district, canonical_school_id, canonical_school_name,
sessions_completed, sessions_missed, attendance_rate, unique_students,
tutoring_minutes`
- `sessions_completed` / `sessions_missed`: distinct sessions contributing at
  least one row to the group.
- `attendance_rate`: attended rows / all rows in COMPLETED sessions, 4 decimals
  (`0.7613`); blank when the denominator is 0.
- `tutoring_minutes`: sum of the session's `length_minutes` over **attended** rows.

**`tutor_conflicts.csv`** — program-integrity report: a human tutor booked in
overlapping sessions. Consider **COMPLETED** sessions only; compare scheduled
intervals `[start_scheduled, start_scheduled + length_minutes)` within a
source_system per tutor. **Cognivo facilitator id `1` is the AI facilitator and
runs many groups concurrently by design — exclude it.** One row per pair with
`session_id_1 < session_id_2`; sort by all four key columns.
`source_system, tutor_pseudo_id, session_id_1, session_id_2, overlap_minutes`

**`dq_findings.csv`** — machine-readable anomaly log; anything you find beyond
the mandated findings goes here too (this is where discovery credit comes from).
`rule_id, severity, source_system, record_ref, note`
- `severity` ∈ `INFO|WARN|ERROR`; `rule_id` is your own short code.
- `record_ref`: `vendor:session_id[:student_pseudo_id]`, `file:<relpath>`,
  `school:<name>`, `district:<name>`, or `date:<YYYY-MM-DD>`.
- Mandated at minimum: `UNMAPPED_SCHOOL`, `CONFLICTING_XWALK`,
  `CONFLICTING_RECORDS`, file-quarantine findings.

**`quarantine/quarantined_rows.csv`** — every quarantined physical row *and*
file. Multiple rows may therefore share a `record_ref` (for example, all
records in an unresolvable duplicate set):
`source_system, record_ref, reason_code, detail` with `reason_code` ∈
`EMPTY_FILE | MALFORMED_FILE | UNKNOWN_FEED | UNPARSEABLE_ROW |
CONFLICTING_RECORDS | OTHER`. Copy quarantined files under
`quarantine/files/`.
