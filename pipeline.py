#!/usr/bin/env python3
"""
Your pipeline entry point.

`python pipeline.py` is exactly how the self-check, CI, and the reviewers run
your submission. Read the five environment variables below, read the vendor
drops, and write the six output files described in output_spec.md. Replace the
body — this skeleton intentionally produces no output so the checks read 0/6
until you implement it.

Run it yourself with:
    python checks/public_checks.py --data sample
(which sets the environment for you), or set the variables and run directly.
"""

import os
import sys


def main():
    default_data = "full" if os.path.isdir("full/landing") else "sample"
    # Inputs
    landing = os.environ.get("LANDING_DIR", f"{default_data}/landing")
    reference = os.environ.get("REFERENCE_DIR", f"{default_data}/reference")
    # Outputs
    output_dir = os.environ.get("OUTPUT_DIR", "outputs")
    quarantine_dir = os.environ.get("QUARANTINE_DIR", "quarantine")
    # Secret salt for pseudonymizing student/tutor ids (see output_spec.md §6)
    salt = os.environ.get("PSEUDONYM_SALT")
    if not salt:
        sys.exit("PSEUDONYM_SALT is not set. Set it to any string first "
                 "(the self-check and CI set it for you).")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(quarantine_dir, exist_ok=True)

    # TODO: implement the pipeline. Produce, per output_spec.md:
    #   <OUTPUT_DIR>/sessions.csv
    #   <OUTPUT_DIR>/attendance.csv
    #   <OUTPUT_DIR>/program_summary.csv
    #   <OUTPUT_DIR>/tutor_conflicts.csv
    #   <OUTPUT_DIR>/dq_findings.csv
    #   <QUARANTINE_DIR>/quarantined_rows.csv
    raise NotImplementedError(
        f"Implement your pipeline. Read drops from {landing} and the crosswalk "
        f"from {reference}; write outputs to {output_dir} and quarantine to "
        f"{quarantine_dir}. See output_spec.md.")


if __name__ == "__main__":
    main()
