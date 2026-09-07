"""Generate and ingest synthetic-but-valid contracts for a local organization.

No LLM involved: this builds ``ContractCandidate`` objects directly and runs
them through the same ``ingest_contract_handler`` the extraction agent uses,
then binds each contract to the target organization so it shows in the portal.

Idempotent - each contract's source hash is derived from ``--seed`` and its
index, so re-running the same seed skips contracts that already exist.

    uv run python synthetic_data_loader/seed_contracts.py --count 120
    uv run python synthetic_data_loader/seed_contracts.py --count 120 --organization-name Capstone
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import random
import sqlite3
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from clm_mcp_server.dependencies import build_dependencies
from clm_mcp_server.ingest_contract_handler import ingest_contract
from clm_mcp_server.ingest_payload import (
    ContractCandidate,
    ExtractedClause,
    ExtractedCommercialTerms,
    ExtractedKeyDates,
    ExtractedObligation,
    ExtractedParty,
    ExtractedSigner,
)

DEFAULT_DATABASE_PATH = str(Path(__file__).parent.parent / "clm.sqlite3")

_PREFIX = [
    "Northwind", "Contoso", "Fabrikam", "Adventure", "Tailspin", "Wingtip", "Proseware", "Litware",
    "Coho", "Fourth Coffee", "Graphic Design", "Blue Yonder", "Alpine", "Trey", "Woodgrove", "Margie's",
    "Lucerne", "Humongous", "Wide World", "First Line", "Consolidated", "Southridge", "Nod",
]
_SUFFIX = ["Inc.", "LLC", "Corp.", "Ltd.", "Group", "Holdings", "Technologies", "Partners", "Systems", "International"]
_INDUSTRY = ["Logistics", "Analytics", "Media", "Foods", "Robotics", "Health", "Financial", "Energy", "Retail", "Cloud", "Manufacturing", "Pharma"]

_CONTRACT_TYPES = {
    "vendor-agreement": (("customer", "vendor"), "Vendor Agreement"),
    "services-agreement": (("client", "service-provider"), "Services Agreement"),
    "master-services-agreement": (("client", "service-provider"), "Master Services Agreement"),
    "affiliate-agreement": (("company", "affiliate"), "Affiliate Agreement"),
    "co-branding-agreement": (("partner", "partner"), "Co-Branding Agreement"),
    "reseller-agreement": (("supplier", "reseller"), "Reseller Agreement"),
    "license-agreement": (("licensor", "licensee"), "License Agreement"),
    "nda": (("disclosing-party", "receiving-party"), "Mutual Nondisclosure Agreement"),
    "distribution-agreement": (("manufacturer", "distributor"), "Distribution Agreement"),
    "amendment": (("customer", "vendor"), "Amendment"),
}

_CLAUSES = [
    ("Payment Terms", "obligation", "Customer shall pay all undisputed invoices within thirty (30) days of receipt."),
    ("Governing Law", "general_provision", "This Agreement is governed by and construed under the laws of the State of Delaware, without regard to its conflict-of-laws rules."),
    ("Term and Termination", "condition", "This Agreement continues for the Initial Term and renews for successive one-year periods unless either party gives sixty (60) days' written notice."),
    ("Confidentiality", "obligation", "Each party shall protect the other party's Confidential Information and use it solely to perform this Agreement."),
    ("Limitation of Liability", "remedy", "Except for breaches of confidentiality, neither party's aggregate liability under this Agreement exceeds the fees paid in the twelve (12) months preceding the claim."),
    ("Indemnification", "obligation", "Each party shall defend and indemnify the other against third-party claims arising from its breach of this Agreement or its gross negligence."),
    ("Intellectual Property", "right", "Each party retains all right, title, and interest in its pre-existing intellectual property."),
    ("Warranties", "obligation", "Each party represents and warrants that it has full authority to enter into and perform this Agreement."),
    ("Force Majeure", "general_provision", "Neither party is liable for failure or delay caused by events beyond its reasonable control, provided it resumes performance promptly."),
    ("Assignment", "condition", "Neither party may assign this Agreement without the other party's prior written consent, except to a successor in a merger or sale of substantially all assets."),
    ("Notices", "general_provision", "All notices must be in writing and delivered by courier or email to the addresses set forth in the preamble."),
    ("Data Protection", "obligation", "The parties shall comply with all applicable data-protection laws and implement appropriate technical and organizational safeguards."),
    ("Insurance", "obligation", "The Vendor shall maintain commercial general liability insurance of not less than $2,000,000 per occurrence during the Term."),
    ("Dispute Resolution", "general_provision", "The parties shall attempt good-faith negotiation before commencing binding arbitration under the AAA Commercial Rules."),
]

_OBLIGATIONS = [
    ("Deliver monthly service report", "monthly"),
    ("Pay the quarterly subscription fee", "quarterly"),
    ("Complete the annual security assessment", "annually"),
    ("Provide the implementation milestone deliverables", None),
    ("Reconcile and true-up usage charges", "quarterly"),
    ("Renew the certificate of insurance", "annually"),
]

_CURRENCIES = ["USD", "USD", "USD", "EUR", "GBP"]
_PAYMENT_TERMS = ["Net 30", "Net 45", "Net 60", "Milestone-based", "Annual in advance"]


def _company(rng: random.Random) -> str:
    return f"{rng.choice(_PREFIX)} {rng.choice(_INDUSTRY)} {rng.choice(_SUFFIX)}"


def _short(name: str) -> str:
    return " ".join(name.split()[:-1]) or name


def _generate(index: int, seed: str) -> ContractCandidate:
    rng = random.Random(f"{seed}:{index}")
    contract_type = rng.choice(list(_CONTRACT_TYPES))
    (role_a, role_b), label = _CONTRACT_TYPES[contract_type]

    name_a, name_b = _company(rng), _company(rng)
    while name_b == name_a:
        name_b = _company(rng)

    parties = [
        ExtractedParty(legal_name=name_a, roles=[role_a], country_code=rng.choice(["US", "US", "GB", "DE"])),
        ExtractedParty(legal_name=name_b, roles=[role_b], country_code=rng.choice(["US", "US", "IE"])),
    ]
    if rng.random() < 0.15:
        parties.append(ExtractedParty(legal_name=_company(rng), roles=["guarantor"]))

    single_party = rng.random() < 0.05
    if single_party:
        parties = parties[:1]

    execution = date(2019, 1, 1) + timedelta(days=rng.randint(0, 2735))  # through mid-2026
    effective = execution + timedelta(days=rng.randint(0, 30))
    expiration = None
    if rng.random() < 0.8:
        expiration = effective + timedelta(days=365 * rng.choice([1, 1, 2, 3, 5]))

    headings = ["Payment Terms", "Governing Law", "Term and Termination"]
    extras = [c for c in _CLAUSES if c[0] not in headings]
    rng.shuffle(extras)
    chosen = [c for c in _CLAUSES if c[0] in headings] + extras[: rng.randint(2, 6)]
    clauses = [
        ExtractedClause(heading=h, clause_type=t, page_location=f"page {n + 1}", text=body)
        for n, (h, t, body) in enumerate(chosen)
    ]

    obligations: list[ExtractedObligation] = []
    if not single_party:
        for description, recurrence in rng.sample(_OBLIGATIONS, rng.randint(1, 3)):
            obligations.append(
                ExtractedObligation(
                    description=description,
                    responsible_party_legal_name=rng.choice([name_a, name_b]),
                    due_date=effective + timedelta(days=rng.randint(30, 400)),
                    recurrence_frequency=recurrence,
                )
            )

    signers: list[ExtractedSigner] = []
    if not single_party and rng.random() < 0.8:
        signers = [
            ExtractedSigner(party_legal_name=name_a, signer_role=role_a, order=1, signed_at=execution),
            ExtractedSigner(party_legal_name=name_b, signer_role=role_b, order=2, signed_at=execution),
        ]

    commercial = ExtractedCommercialTerms()
    if rng.random() < 0.85:
        commercial = ExtractedCommercialTerms(
            total_value_amount=rng.choice([25_000, 50_000, 120_000, 250_000, 480_000, 1_200_000, 3_500_000]),
            total_value_currency=rng.choice(_CURRENCIES),
            payment_terms=rng.choice(_PAYMENT_TERMS),
        )

    title = f"{_short(name_a)} - {_short(name_b)} {label}"
    source_hash = hashlib.sha256(f"{seed}:seed-contract:{index:05d}".encode()).hexdigest()
    payload = {
        "title": title,
        "contract_type": contract_type,
        "parties": [p.model_dump(mode="json") for p in parties],
        "clauses": [c.model_dump(mode="json") for c in clauses],
        "generated": True,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode()

    return ContractCandidate(
        source_document_hash=source_hash,
        source_uri=f"seed://capstone/contract-{index:05d}.json",
        source_media_type="application/json",
        source_content_base64=base64.b64encode(blob).decode("ascii"),
        source_original_filename=f"seed-contract-{index:05d}.json",
        title=title,
        contract_type=contract_type,
        parties=parties,
        clauses=clauses,
        obligations=obligations,
        signers=signers,
        key_dates=ExtractedKeyDates(effective_date=effective, execution_date=execution, expiration_date=expiration),
        commercial_terms=commercial,
    )


def _resolve_org(database_path: str, organization_id: str | None, organization_name: str | None) -> str:
    connection = sqlite3.connect(database_path)
    try:
        if organization_id:
            return organization_id
        if organization_name:
            row = connection.execute("SELECT id FROM organizations WHERE name = ?", (organization_name,)).fetchone()
            if row:
                return row[0]
            raise SystemExit(f"No organization named {organization_name!r}. Run scripts\\run-all.ps1 -Bootstrap first.")
        rows = connection.execute("SELECT id, name FROM organizations ORDER BY created_at").fetchall()
        if len(rows) == 1:
            return rows[0][0]
        raise SystemExit(f"Multiple organizations exist - pass --organization-name or --organization-id: {rows}")
    finally:
        connection.close()


def _reset(database_path: str, organization_id: str) -> int:
    """Delete previously seeded contracts (marked by their seed:// source URI)."""
    connection = sqlite3.connect(database_path)
    try:
        ids = [
            row[0]
            for row in connection.execute(
                "SELECT c.id FROM contracts c JOIN contract_tenants t ON t.contract_id = c.id "
                "WHERE t.organization_id = ? AND c.data LIKE '%seed://capstone/%'",
                (organization_id,),
            )
        ]
        for contract_id in ids:
            connection.execute("DELETE FROM contract_tenants WHERE contract_id = ?", (contract_id,))
            connection.execute("DELETE FROM domain_events WHERE aggregate_id = ?", (contract_id,))
            connection.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))
        connection.execute("DELETE FROM document_blobs WHERE original_filename LIKE 'seed-contract-%'")
        connection.commit()
        return len(ids)
    finally:
        connection.close()


def _bind(database_path: str, contract_ids: list[str], organization_id: str) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.executemany(
            "INSERT OR IGNORE INTO contract_tenants (contract_id, organization_id, created_at) VALUES (?, ?, datetime('now'))",
            [(cid, organization_id) for cid in contract_ids],
        )
        connection.commit()
    finally:
        connection.close()


def seed(database_path: str, count: int, seed_value: str, organization_id: str) -> dict[str, Any]:
    deps = build_dependencies(database_path)
    statuses: Counter[str] = Counter()
    types: Counter[str] = Counter()
    contract_ids: list[str] = []
    reused = 0

    for index in range(count):
        candidate = _generate(index, seed_value)
        try:
            result = ingest_contract(candidate, deps)
        except Exception as error:  # noqa: BLE001 - report and continue
            statuses[f"error:{type(error).__name__}"] += 1
            print(f"  {index + 1}/{count} FAILED {type(error).__name__}: {error}", flush=True)
            continue
        contract_ids.append(result.contract_id)
        statuses[result.lifecycle_status] += 1
        types[candidate.contract_type] += 1
        reused += 1 if result.already_ingested else 0
        if (index + 1) % 20 == 0:
            print(f"  {index + 1}/{count} ingested", flush=True)

    _bind(database_path, contract_ids, organization_id)
    return {
        "requested": count,
        "ingested": len(contract_ids),
        "already_present": reused,
        "organization_id": organization_id,
        "lifecycle_status": dict(statuses.most_common()),
        "contract_type": dict(types.most_common()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--seed", default="capstone-2026")
    parser.add_argument("--database-path", default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--organization-id", default=None)
    parser.add_argument("--organization-name", default="Capstone")
    parser.add_argument("--reset", action="store_true", help="Delete previously seeded contracts first")
    args = parser.parse_args()

    organization_id = _resolve_org(args.database_path, args.organization_id, args.organization_name)
    if args.reset:
        removed = _reset(args.database_path, organization_id)
        print(f"Removed {removed} previously seeded contracts")
    print(f"Seeding {args.count} contracts into {args.database_path} for org {organization_id}")
    summary = seed(args.database_path, args.count, args.seed, organization_id)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
