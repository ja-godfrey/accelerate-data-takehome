# Convenience wrappers. Everything here is a one-line Python command you can
# also run directly (no `make` required — handy on Windows).

data:        ## download the full dataset (~30 MB zip) into full/
	python get_data.py

run:         ## run via the checker, which sets paths + a local pseudonym salt
	python checks/public_checks.py --data auto

check:       ## public checks on the small in-repo sample (fast loop)
	python checks/public_checks.py --data sample

check-full:  ## public checks on the full dataset
	python checks/public_checks.py --data full

.PHONY: data run check check-full
