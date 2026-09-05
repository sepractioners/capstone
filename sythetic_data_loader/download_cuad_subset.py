"""Downloads the CUAD (Contract Understanding Atticus Dataset) via
kagglehub and copies a chosen category subset's PDFs into
sythetic_data_loader/data/cuad_subset/ for the extraction pipeline to
process.

The full dataset is ~107MB and downloads as one unit regardless of which
categories you want - this script just controls which categories get
copied locally, so a first run stays fast.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import kagglehub

DATASET_REF = "konradb/atticus-open-contract-dataset-aok-beta"
DEFAULT_CATEGORIES = ["Affiliate_Agreements", "Co_Branding"]
OUTPUT_DIR = Path(__file__).parent / "data" / "cuad_subset"


def download_subset(categories: list[str] = DEFAULT_CATEGORIES) -> Path:
    dataset_root = Path(kagglehub.dataset_download(DATASET_REF))
    pdf_root = dataset_root / "CUAD_v1" / "full_contract_pdf" / "Part_I"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for category in categories:
        category_dir = pdf_root / category
        if not category_dir.exists():
            print(f"warning: category not found under Part_I: {category}")
            continue
        for pdf in category_dir.glob("*.pdf"):
            shutil.copy2(pdf, OUTPUT_DIR / pdf.name)
            copied += 1

    print(f"Copied {copied} PDFs from {categories} into {OUTPUT_DIR}")
    return OUTPUT_DIR


if __name__ == "__main__":
    download_subset(sys.argv[1:] or DEFAULT_CATEGORIES)
