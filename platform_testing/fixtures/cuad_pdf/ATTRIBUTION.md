# CUAD sample contracts — attribution

The 8 PDF files in this directory are an unmodified subset of the **Contract
Understanding Atticus Dataset (CUAD) v1**.

- **Source:** The Atticus Project — <https://www.atticusprojectai.org/cuad>,
  <https://github.com/TheAtticusProject/cuad>,
  <https://huggingface.co/datasets/theatticusproject/cuad>
- **Licence:** Creative Commons Attribution 4.0 International (CC BY 4.0) —
  <https://creativecommons.org/licenses/by/4.0/>
- **Citation:**

  > Hendrycks, D., Burns, C., Chen, A., & Ball, S. (2021). *CUAD: An
  > Expert-Annotated NLP Dataset for Legal Contract Review.* arXiv:2103.06268.

## What was taken and changed

- **Taken:** 8 contract PDFs (5 co-branding, 3 affiliate agreements), copied
  verbatim from CUAD's `full_contract_pdf/` tree. No modification to the files.
- **Added, not part of CUAD:** `../cuad_ground_truth.jsonl` — our own
  hand-authored field labels (title, parties, contract_type, effective_date)
  for these 8 contracts, used by `platform_testing/extraction_eval.py`. CUAD's
  own clause annotations are not reproduced here.

The underlying contracts are public filings from the U.S. SEC EDGAR system. The
Atticus Project makes no representations about their copyright status; only
derived structured labels and these public filings are redistributed here.
