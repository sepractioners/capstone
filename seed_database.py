#!/usr/bin/env python3
"""Seed CLM database with tenant data, CUAD contracts, and RAG indices."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

# Web database setup
from web.clm_web.db import WebDatabase

# RAG setup
from agents.extraction_agent.hybrid_rag import initialize as initialize_rag, add_records as add_rag_records
from agents.extraction_agent.loaders import _load_pdf

# Kaggle CUAD dataset
from synthetic_data_loader.download_cuad_subset import download_subset, download_all

logger = logging.getLogger(__name__)

CAPSTONE_ORG_ID = "capstone"
CAPSTONE_USER_ID = "admin-capstone-local"
CAPSTONE_USER_EMAIL = "admin@capstone.local"
CAPSTONE_ORG_NAME = "Capstone"
CAPSTONE_USER_PASSWORD = "CapstoneAdmin!2026"

DEFAULT_CUAD_CATEGORIES = ["Affiliate_Agreements", "Co_Branding", "License_Agreements"]
DEFAULT_CUAD_LIMIT = 10


def download_cuad_contracts(
    categories: list[str] | None = None,
    limit: int | None = None,
    data_dir: str | Path | None = None
) -> Path:
    """Download CUAD contract PDFs from Kaggle.

    Args:
        categories: List of CUAD categories to download (None for defaults)
        limit: Maximum number of PDFs to download
        data_dir: Output directory for PDFs

    Returns:
        Path to directory containing downloaded PDFs
    """
    if data_dir is None:
        data_dir = Path(__file__).parent / "synthetic_data_loader" / "data" / "cuad_subset"

    data_dir.mkdir(parents=True, exist_ok=True)

    if categories is None:
        categories = DEFAULT_CUAD_CATEGORIES

    print(f"Downloading {len(categories)} CUAD categories...")
    print(f"  Categories: {', '.join(categories)}")

    try:
        result_dir = download_subset(categories, limit=limit)
        print(f"✓ Downloaded contracts to {result_dir}")
        return result_dir
    except Exception as e:
        logger.warning(f"Failed to download CUAD: {e}")
        print(f"⚠ CUAD download failed: {e}")
        print("  Ensure Kaggle credentials are configured (kagglehub.cache_dir)")
        raise


def extract_contract_from_pdf(pdf_path: Path) -> dict | None:
    """Extract text and metadata from a PDF contract.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Dictionary with contract data or None if extraction fails
    """
    try:
        chunks = _load_pdf(pdf_path)
        if not chunks:
            return None

        # Get first page as sample text
        first_page = chunks[0].text if chunks else ""
        if not first_page:
            return None

        # Combine first few chunks for better context
        full_text = "\n".join(chunk.text for chunk in chunks[:3])

        return {
            "id": f"cuad:{pdf_path.stem}",
            "name": pdf_path.stem.replace("_", " "),
            "source": str(pdf_path),
            "knowledge_type": "kaggle_example",
            "contract_type": "unclassified",
            "dataset": "cuad",
            "text": first_page[:12000],  # First page for retrieval
            "full_text": full_text[:50000],  # More context for RAG
            "required_fields": ["parties", "effective_date", "termination_clause"],
            "recommended_fields": ["payment_terms", "confidentiality", "liability_limits"],
        }
    except Exception as e:
        logger.debug(f"Failed to extract {pdf_path}: {e}")
        return None


def load_cuad_to_rag(
    data_dir: Path | str,
    rag_db_path: Path | str,
) -> list[dict]:
    """Load CUAD PDFs into RAG database.

    Args:
        data_dir: Directory containing PDF files
        rag_db_path: Path to RAG SQLite database

    Returns:
        List of loaded records
    """
    data_dir = Path(data_dir)
    records = []

    print(f"Extracting and indexing CUAD contracts...")
    pdfs = sorted(data_dir.glob("*.pdf"))

    if not pdfs:
        print(f"⚠ No PDF files found in {data_dir}")
        return records

    print(f"  Found {len(pdfs)} PDF files")

    for idx, pdf_path in enumerate(pdfs, 1):
        print(f"    [{idx}/{len(pdfs)}] {pdf_path.name}...", end=" ", flush=True)

        contract_data = extract_contract_from_pdf(pdf_path)
        if contract_data:
            records.append(contract_data)
            print("✓")
        else:
            print("⊘ (skipped)")

    if records:
        print(f"  Indexing {len(records)} contracts in RAG database...")
        add_rag_records(records, rag_db_path)
        print(f"✓ Added {len(records)} contracts to RAG")

    return records


SAMPLE_RAG_KNOWLEDGE = [
    {
        "id": "knowledge:contract_types",
        "name": "Common Contract Types",
        "knowledge_type": "contract_profile",
        "contract_type": "service_agreement",
        "dataset": "internal",
        "text": """Service Agreement - A contract between a service provider and client defining the scope of services, deliverables, payment terms, and performance expectations. Key clauses include scope of work, payment terms, confidentiality, intellectual property, term and termination, limitation of liability, and dispute resolution. Required fields: service description, parties, fees, term. Recommended fields: SLAs, performance metrics, change orders.""",
        "required_fields": ["service_description", "parties", "fees", "term"],
        "recommended_fields": ["slas", "performance_metrics", "change_orders", "insurance", "indemnification"],
        "guidance": "Service agreements should clearly define the scope of work, deliverables, timeline, and payment structure. Ensure SLAs are specific and measurable."
    },
    {
        "id": "knowledge:nda_best_practices",
        "name": "NDA Best Practices",
        "knowledge_type": "contract_profile",
        "contract_type": "nda",
        "dataset": "internal",
        "text": """Non-Disclosure Agreement (NDA) - A confidentiality agreement protecting sensitive business information shared between parties. Key clauses include definition of confidential information, permitted use, exclusions, term of confidentiality, remedies, and return of materials. Required fields: parties, information type, term. Recommended fields: permitted disclosures, remedies, governing law, dispute resolution. NDAs can be unilateral (one-way) or mutual (two-way).""",
        "required_fields": ["parties", "definition_of_confidential_info", "term"],
        "recommended_fields": ["exclusions", "permitted_use", "remedies", "jurisdiction"],
        "guidance": "Define 'Confidential Information' clearly to avoid disputes. Specify the term of confidentiality and permitted uses. Consider including permitted disclosures to legal counsel, advisors, and required regulatory disclosures."
    },
    {
        "id": "knowledge:license_clauses",
        "name": "Software License Key Terms",
        "knowledge_type": "contract_profile",
        "contract_type": "license_agreement",
        "dataset": "internal",
        "text": """Software License Agreement - Grant of rights to use software under defined restrictions. Key clauses include grant of license, scope of use, restrictions, intellectual property, fees, support/updates, warranty disclaimers, limitation of liability, and termination. Common license types: perpetual vs. term-based, exclusive vs. non-exclusive, single-user vs. multi-user. Required fields: licensor, licensee, software scope, fees, term. Recommended fields: usage restrictions, IP ownership, support level, upgrade policy.""",
        "required_fields": ["licensor", "licensee", "software_description", "fees", "license_type"],
        "recommended_fields": ["usage_restrictions", "update_policy", "support_level", "compliance", "audit_rights"],
        "guidance": "Clearly define license scope: number of users, deployment environments, permitted uses. Address intellectual property ownership for custom modifications. Include support and update terms. Define data retention and deletion policies."
    },
    {
        "id": "knowledge:payment_terms",
        "name": "Standard Payment Terms",
        "knowledge_type": "procedural",
        "contract_type": "general",
        "dataset": "internal",
        "text": """Payment terms define when and how compensation is due. Common terms include Net 30 (payment due within 30 days), Net 60, Net 90, due upon receipt, and monthly/quarterly billing. Payment methods: wire transfer, ACH, credit card, check. Late payment interest: typically 1-2% per month. Invoicing frequency: upon completion, monthly, quarterly, or annually. Payment schedule should align with deliverable milestones to manage cash flow. Consider retainage provisions for long-term contracts. Specify currency and location of payment.""",
        "required_fields": ["payment_terms", "currency"],
        "recommended_fields": ["late_payment_interest", "payment_method", "invoicing_frequency"],
        "guidance": "Specify payment terms clearly to avoid disputes. Consider Net 30 as standard for services. For large contracts, tie payments to milestone completion. Include provisions for late payment interest and dispute resolution."
    }
]


def create_web_database(db_path: str) -> WebDatabase:
    """Initialize the web application database."""
    print(f"Creating web database at {db_path}...")
    db = WebDatabase(db_path)
    return db


def seed_web_database(db_path: str, cuad_records: list[dict] | None = None) -> None:
    """Add sample tenant, users, and CUAD contracts to the web database.

    Args:
        db_path: Path to web database
        cuad_records: List of CUAD contract records from RAG indexing
    """
    print("Seeding web database with tenant data...")
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        now = datetime.now(timezone.utc).isoformat()

        # Check if already seeded
        org_count = connection.execute("SELECT COUNT(*) as cnt FROM organizations").fetchone()[0]
        if org_count > 0:
            print("✓ Web database already seeded, skipping...")
            return

        # Add Capstone organization/tenant
        print(f"  Adding organization: {CAPSTONE_ORG_NAME}")
        connection.execute(
            "INSERT INTO organizations (id, name, created_at) VALUES (?, ?, ?)",
            (CAPSTONE_ORG_ID, CAPSTONE_ORG_NAME, now)
        )

        # Add admin user
        print(f"  Adding admin user: {CAPSTONE_USER_EMAIL}")
        from hashlib import sha256
        password_hash = sha256(CAPSTONE_USER_PASSWORD.encode()).hexdigest()
        connection.execute(
            "INSERT INTO users (id, email, password_hash, display_name, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (CAPSTONE_USER_ID, CAPSTONE_USER_EMAIL, password_hash, "Admin", 1, now)
        )

        # Add membership
        connection.execute(
            "INSERT INTO memberships (user_id, organization_id, role) VALUES (?, ?, ?)",
            (CAPSTONE_USER_ID, CAPSTONE_ORG_ID, "admin")
        )

        # Add CUAD contracts if provided
        if cuad_records:
            print(f"  Adding {len(cuad_records)} CUAD contracts...")
            for record in cuad_records:
                contract_id = record["id"]
                connection.execute(
                    "INSERT OR IGNORE INTO contract_tenants (contract_id, organization_id, created_at) VALUES (?, ?, ?)",
                    (contract_id, CAPSTONE_ORG_ID, now)
                )

        connection.commit()
        print("✓ Web database seeded successfully")
    finally:
        connection.close()


def seed_rag_database(db_path: str) -> None:
    """Add sample knowledge records to the RAG retrieval database."""
    print("Seeding RAG knowledge base...")

    # Initialize RAG database
    connection = initialize_rag(db_path)
    connection.close()

    # Check if already seeded
    connection = sqlite3.connect(db_path)
    existing = connection.execute("SELECT COUNT(*) as cnt FROM rag_documents").fetchone()[0]
    connection.close()

    if existing > 0:
        print("✓ RAG database already seeded, skipping...")
        return

    # Add knowledge records
    print(f"  Adding {len(SAMPLE_RAG_KNOWLEDGE)} knowledge records...")
    for record in SAMPLE_RAG_KNOWLEDGE:
        print(f"    - {record['name']}")

    add_rag_records(SAMPLE_RAG_KNOWLEDGE, db_path)
    print("✓ RAG knowledge base seeded successfully")


def create_rag_vector_index(db_path: str, index_path: str | None = None) -> None:
    """Build FAISS vector index from RAG embeddings (optional)."""
    try:
        from agents.extraction_agent.faiss_backend import build_index

        if index_path is None:
            index_path = "synthetic_data_loader/rag_knowledge.faiss"

        index_file = Path(index_path)
        if index_file.exists():
            print(f"✓ FAISS index already exists at {index_path}")
            return

        print(f"Building FAISS vector index...")
        index_file = build_index(db_path, index_path)
        print(f"✓ FAISS index created at {index_file}")
    except ImportError:
        print("⚠ FAISS not installed; skipping vector index creation")
        print("  Install with: pip install faiss-cpu")
    except Exception as e:
        print(f"⚠ Could not build FAISS index: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Seed CLM database with tenant data, CUAD contracts, and RAG indices"
    )
    parser.add_argument(
        "--web-db",
        default="data/clm_web.sqlite3",
        help="Path to web application database (default: data/clm_web.sqlite3)"
    )
    parser.add_argument(
        "--rag-db",
        default="synthetic_data_loader/rag_knowledge.sqlite3",
        help="Path to RAG knowledge database (default: synthetic_data_loader/rag_knowledge.sqlite3)"
    )
    parser.add_argument(
        "--faiss-index",
        default="synthetic_data_loader/rag_knowledge.faiss",
        help="Path to FAISS vector index (default: synthetic_data_loader/rag_knowledge.faiss)"
    )
    parser.add_argument(
        "--cuad-dir",
        default=None,
        help="Directory containing CUAD PDF files (auto-downloads if not specified)"
    )
    parser.add_argument(
        "--cuad-categories",
        nargs="+",
        default=DEFAULT_CUAD_CATEGORIES,
        help=f"CUAD categories to download (default: {DEFAULT_CUAD_CATEGORIES})"
    )
    parser.add_argument(
        "--cuad-limit",
        type=int,
        default=DEFAULT_CUAD_LIMIT,
        help=f"Max CUAD PDFs to download (default: {DEFAULT_CUAD_LIMIT})"
    )
    parser.add_argument(
        "--skip-cuad",
        action="store_true",
        help="Skip CUAD dataset download and seeding"
    )
    parser.add_argument(
        "--skip-rag",
        action="store_true",
        help="Skip RAG knowledge base seeding"
    )
    parser.add_argument(
        "--skip-faiss",
        action="store_true",
        help="Skip FAISS vector index creation"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    print("=" * 70)
    print("CLM Database Seeding with Kaggle CUAD Dataset")
    print("=" * 70)

    # Create directories
    Path(args.web_db).parent.mkdir(parents=True, exist_ok=True)
    Path(args.rag_db).parent.mkdir(parents=True, exist_ok=True)

    cuad_records = []

    # Download and index CUAD contracts
    if not args.skip_cuad:
        try:
            if args.cuad_dir and Path(args.cuad_dir).exists():
                cuad_dir = Path(args.cuad_dir)
                print(f"\nUsing existing CUAD directory: {cuad_dir}")
            else:
                cuad_dir = download_cuad_contracts(
                    categories=args.cuad_categories,
                    limit=args.cuad_limit
                )

            if not args.skip_rag:
                cuad_records = load_cuad_to_rag(cuad_dir, args.rag_db)
        except Exception as e:
            print(f"\n⚠ CUAD seeding failed: {e}")
            print("  Continuing with web database and procedural knowledge only...")
            args.skip_cuad = True

    # Seed web database
    db = create_web_database(args.web_db)
    seed_web_database(args.web_db, cuad_records)

    # Seed RAG procedural knowledge
    if not args.skip_rag and not cuad_records:
        print()
        seed_rag_database(args.rag_db)
    elif not args.skip_rag and cuad_records:
        # Still seed procedural knowledge
        print("Adding procedural knowledge to RAG...")
        connection = initialize_rag(args.rag_db)
        connection.close()
        add_rag_records(SAMPLE_RAG_KNOWLEDGE, args.rag_db)
        print(f"✓ Added {len(SAMPLE_RAG_KNOWLEDGE)} procedural knowledge records")

    # Build FAISS index
    if not args.skip_rag and not args.skip_faiss:
        create_rag_vector_index(args.rag_db, args.faiss_index)

    print("\n" + "=" * 70)
    print("Seeding Complete")
    print("=" * 70)
    print(f"\nWeb Database:      {Path(args.web_db).resolve()}")
    print(f"RAG Database:      {Path(args.rag_db).resolve()}")
    if not args.skip_faiss:
        print(f"FAISS Index:       {Path(args.faiss_index).resolve()}")
    print(f"\nCapstone Organization: {CAPSTONE_ORG_NAME}")
    print(f"Admin User:            {CAPSTONE_USER_EMAIL}")
    print(f"Admin Password:        {CAPSTONE_USER_PASSWORD}")
    print(f"\nKAGGLE CUAD Contracts: {len(cuad_records)}")
    print(f"Procedural Knowledge: {len(SAMPLE_RAG_KNOWLEDGE)} records")
    print("\nNext steps:")
    print("  1. Start the web server: python -m web.clm_web.server")
    print("  2. Access the application at https://localhost:5173")
    print(f"  3. Login with {CAPSTONE_USER_EMAIL} / {CAPSTONE_USER_PASSWORD}")


if __name__ == "__main__":
    main()
