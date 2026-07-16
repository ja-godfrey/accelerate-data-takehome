# Vendor Feed Layouts

Four tutoring providers upload monthly drops to Accelerate's SFTP. One folder
per month (`landing/2025-12/`, `landing/2026-01/`, ...). Files are grain
**one row per student per session** — session-level values repeat on every row
of a session. Every feed carries a row-level `exported_at` (when the vendor
generated the file). Vendors occasionally re-send files, send corrections in a
later drop, rename columns between drops, and deliver files that failed in
transfer. Your pipeline is expected to survive all of that (see
`output_spec.md`).

Reference data: `school_crosswalk.csv` maps each vendor's school reference
(name or campus code) to canonical school ids/names
(`source_system, raw_school_ref, canonical_school_id, canonical_school_name`).
Updated versions may arrive inside a monthly drop as `school_crosswalk_v2.csv`.

---

## Northquill Tutoring Co. — `northquill_*.csv`
Comma CSV, UTF-8, ISO timestamps (`YYYY-MM-DD HH:MM:SS`). Human tutors with
personal email addresses. Grades zero-padded (`06`).

`session_id, scheduled_start, actual_start, duration_min, location, status,
session_title, district_id, district_name, program, enrolled_count,
present_count, absent_count, subject, tutor_id, tutor_email, tutor_present,
skills, student_id, roster_status, attended, joined_at, left_at,
minutes_in_session, school_name, grade, section, course, engagement,
skill_progress, exported_at`

Notes: `status` is session-level (`COMPLETED`/`MISSED`). `school_name` is the
student's school as recorded by the vendor's roster system. Column order is not
guaranteed between drops — parse by header.

## Quadrant Learning — `quadrant_*.csv`
Comma CSV, **Windows-1252** encoding, PascalCase headers. Timestamps arrive as
`MM/DD/YYYY HH:MM` in some files and ISO in others. `SessionNotes` is free text
and may span multiple lines (quoted). Schools are identified by `CampusCode`
(crosswalk it). Sends student demographics. All rows are delivered sessions;
absent students appear as `RosterStatus = NO_SHOW`.

`SessionGUID, ScheduledStart, ActualStart, DurationMinutes, Modality,
SessionStatus, District, Program, GroupSize, PresentCount, TutorGUID,
TutorLate, SessionNotes, StudentGUID, RosterStatus, Attended, JoinTime,
LeaveTime, MinutesInSession, CampusCode, GradeLevel, CourseName, Engagement,
Progress, StudentRating, Gender, Ethnicity, ELL, IEP, ExportedAt`

Notes: column names may change slightly between drops (e.g., `GradeLevel` vs
`Grade`) and new columns may appear; parse by header and ignore extras.

## Summit Steps Tutoring — `summitsteps_*.psv`
**Pipe-delimited**, UTF-8, timestamps `MM/DD/YYYY HH:MM`. In-person and online.
Grades arrive unpadded (`6`). Partner organizations appear in `org_name`
(these are the "district" for reporting). Known to rename `grade` →
`grade_level` and append `funding_code` in newer drops.

`session_uid | sched_start | start_actual | len_min | setting | session_state |
session_label | org_name | program_name | group_size | n_present | n_absent |
subject | tutor_uid | tutor_ok | session_notes | skill_list | student_uid |
roster_state | present_flag | join_ts | leave_ts | mins_attended | school_uid |
school_name | grade | section_label | course_name | exported_at`

## Cognivo Labs — `cognivo_*.jsonl`
JSON Lines; one object per student-session row; ISO-8601 `T` timestamps.
AI-facilitated peer groups, variable session lengths (2–25 min). No enrollment
counts and no session-status field (delivered sessions only — treat as
COMPLETED; listed participants attended). **`facilitator.id = "1"` is the AI
facilitator**; other facilitator ids are human coaches.

```json
{"exported_at": "...",
 "session": {"id", "scheduled", "started", "length_min", "modality", "topic",
             "skills": [...], "summary"},
 "org": {"district_id", "district", "program", "school"},
 "facilitator": {"id", "attended"},
 "participant": {"id", "grade", "status", "joined", "left", "minutes"}}
```

Key order varies between rows. `session.summary` is model-generated free text.
