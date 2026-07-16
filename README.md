# Accelerate Data Engineering Take-Home

Accelerate makes grants to tutoring providers and school districts for
high-dosage tutoring, and we need to understand how funded programs are being
implemented. Four providers upload messy, mutually inconsistent session exports
to our SFTP. Your job is to build the pipeline that turns those drops into our
standard reporting tables reliably, repeatably, and without leaking student
data.¹

## What you build

Two deliverables:

1. **A pipeline** — Python 3 — that reads the landing zone and produces the
   outputs defined in **[`output_spec.md`](output_spec.md)**. Feed layouts are
   in **[`vendor_feeds.md`](vendor_feeds.md)**. Your entry point is
   **`pipeline.py`** at the repo root; we run it with `python pipeline.py`.
   The standard library is plenty — if you use packages, list them in
   `requirements.txt`.
2. **A one-page executive memo** (`MEMO.md` or a PDF in the repo) to
   Accelerate's leadership: how we should run this as an ongoing operation —
   receiving and validating future provider drops, storing raw and processed
   data, refreshing the reporting tables, and access/retention/documentation
   and FERPA-compliant handling of student data. Write for senior leaders:
   lead with recommendations, keep implementation detail brief but concrete,
   and state the assumptions, risks, and open questions you hit — including
   anything you left unfinished. One page.

## Getting started

1. Click **Use this template** → create a **private** repo → clone it.
2. `python get_data.py` — downloads the full dataset (~1M rows) into `full/`.
   A small `sample/` ships in-repo for fast iteration.
3. Write your `pipeline.py`, then check yourself:
   `python checks/public_checks.py --data sample` (or `--data full`).
4. Push — CI runs the same checks and posts your result on every commit.

## Scoring

You get a visible conformance gate and a separately scored hidden evaluation.
The public checks carry no points; they give fast feedback on whether your
outputs honor the interface.

- **Public checks — six conformance checks** (`checks/public_checks.py`, runs
  in CI on every push): output files present, columns match the spec, rows
  sorted and keys unique, ids pseudonymized with the requested salt and no raw
  identifiers/emails, quarantine and
  findings files well-formed, and the pipeline re-runs byte-identically. These
  confirm your output fits the contract — they do **not** check whether your
  numbers are correct or tell you what's wrong with the data. Finding that is
  the job.
- **Hidden evaluation**: after you submit, we run
  your repo unmodified against a dataset you have not seen — same feeds, same
  contract, new data, new surprises within the documented rules. Cell-level
  accuracy against ground truth, incident handling, idempotency and PII gates,
  runtime. The discovery bonus rewards real anomalies you log in
  `dq_findings.csv`. **Hardcoding to the sample or full data will show here.**

  The hidden score is deliberately split so one production-scale failure does
  not erase everything else. A compact, incident-complete hidden set scores
  cell accuracy, incident handling, idempotency, the PII gate, and discovery
  findings (**70/75 pipeline points**). A separate full-scale run is worth
  **5 runtime points**. A timeout there loses those runtime points only.

The pipeline is worth 75 points. Your code, memo, and the engineering judgment
you demonstrate in the follow-up conversation are reviewed separately (25 points).

| Tier | Meaning |
|---|---|
| Bronze | runs end-to-end, outputs match the contract schema |
| Silver | + idempotent re-runs, clean PII scan, well-formed quarantine/findings |
| Gold | + holds up on the hidden set (weighted cell accuracy >= 90%) |
| Platinum | + fast runtime and real discoveries in your findings |

Aim for Bronze first, then climb. A careful Silver beats a broken Platinum
attempt.

## Ground rules

- **Time limit: ~3 focused hours.** The task is deliberately bigger than the
  time box, and completion is not expected. We care about what you prioritize,
  how effectively you use the available tools, and whether the portion you do
  finish is reliable and explainable. When you hit the limit, stop and note
  what is unfinished and what you would do next in the memo.
- Python 3. We evaluate outputs and behavior, not framework choices; the
  standard library is enough, and any packages go in `requirements.txt`.
- The scoring container provides 2 CPUs, 8 GiB RAM, and 2 GiB writable scratch
  space at `/tmp`. Compact hidden runs have a 10-minute limit; the one full-scale
  benchmark has a 40-minute limit. `OUTPUT_DIR` and `QUARANTINE_DIR` are
  pipeline-owned directories and may be cleared or recreated on a full rebuild.
- AI tools, assistants, and documentation are all fair game; other candidates
  will use them too. In the follow-up conversation, be prepared to explain how
  your pipeline works, the decisions you made, and how you validated it.
- Treat the data as if it were real student records — handling it carelessly
  (including where you send free-text fields) is part of the evaluation.
- Editing `checks/` or the workflow only changes your local feedback; scoring
  runs our own copies.

## Submitting

When you're done — or you hit the time box — package your repository as a **git
bundle** (a single file that carries your code, your memo, and your commit
history) and upload it with the submission form. No repo to share, no
collaborators to add.

From inside your repo:

```bash
git add -A
git commit -m "Final submission"      # if there's nothing to commit, that's fine
git tag submission                     # marks exactly what you're submitting
git bundle create submission.bundle --all
git bundle verify submission.bundle    # should print "...is okay"
```

Then upload `submission.bundle` with the form below:

**Submission form:**
https://docs.google.com/forms/d/e/1FAIpQLSdDRBQK373icJOPNJPuilvppA010dSOnUch8KOBQh3tXZ6iwg/viewform

Google sign-in is required to upload a file; the form records the account email
with the submission.

Your repo must contain `pipeline.py` (plus any modules it imports), a
`requirements.txt` if you used any packages, and the one-page executive memo
(`MEMO.md` or a PDF). The dataset is excluded by `.gitignore`, so the bundle
stays small — don't add it back. Submit by the deadline in your invitation
email. If git gives you trouble, zip the repo folder instead (delete `full/`
and `outputs/` first) and upload the `.zip`.

---
¹ Every district, school, provider, tutor, and student in these files is
synthetic and fictional. No real student data is present — but handle it as if
it were.
