#!/usr/bin/env python3
"""
Download and unpack the full take-home dataset into ./full/.

Cross-platform, standard library only:
    python get_data.py

Produces ./full/landing/ and ./full/reference/ (~1M rows, ~460 MB unpacked).
A small ./sample/ already ships in the repo for fast iteration.
"""

import hashlib
import os
import sys
import urllib.request
import zipfile

DATA_VERSION = "v1"
URL = (f"https://github.com/ja-godfrey/accelerate-data-takehome/releases/download/"
       f"{DATA_VERSION}/accelerate-takehome-full-data.zip")
SHA256 = "5539e8dac236a57fea2bd5fa77b60774ae01778a3e590159c48d9a306aa4d3f1"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    zip_path = os.path.join(here, "_full_data.zip")
    landing = os.path.join(here, "full", "landing")
    crosswalk = os.path.join(here, "full", "reference", "school_crosswalk.csv")
    if os.path.isdir(landing) and os.path.isfile(crosswalk):
        print("./full/ already present — delete it to re-download.")
        return
    if os.path.exists(os.path.join(here, "full")):
        sys.exit("./full/ exists but is incomplete. Delete it, then run this command again.")
    print(f"Downloading full dataset (~30 MB zip):\n  {URL}")
    try:
        urllib.request.urlretrieve(URL, zip_path)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Download failed: {e}\nYou can download the URL above manually "
                 f"and unzip it here so ./full/ exists.")
    digest = sha256(zip_path)
    if digest != SHA256:
        os.remove(zip_path)
        sys.exit(f"Downloaded data failed SHA-256 verification.\nExpected: {SHA256}\n"
                 f"Received: {digest}\nNo files were extracted.")
    print(f"Verified data release {DATA_VERSION}; extracting into ./full/ ...")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(here)
    os.remove(zip_path)
    if not os.path.isdir(landing) or not os.path.isfile(crosswalk):
        sys.exit("The archive extracted but the expected landing/reference files are missing.")
    print("Done. Full dataset is in ./full/ (landing/ + reference/).")


if __name__ == "__main__":
    main()
