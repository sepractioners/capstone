# Database Seeding Guide

This guide explains how to seed the CLM (Contract Lifecycle Management) database with tenant data, Kaggle CUAD contracts, and retrieval/semantic stores.

## Overview

The seeding script initializes four key components:

1. **Kaggle CUAD Contracts**
   - Downloads contract PDFs from Kaggle's Atticus Open Contract Dataset
   - Extracts text and metadata from PDFs
   - Indexes contracts for retrieval

2. **Web Application Database** (`clm_web.sqlite3`)
   - Organizations/Tenants
   - Users
   - Memberships and access control
   - Contract references (linked to CUAD contracts)

3. **RAG Knowledge Base** (`rag_knowledge.sqlite3`)
   - CUAD contract examples for semantic retrieval
   - Procedural knowledge records
   - Full-text search index (FTS5)
   - Vector embeddings for semantic search

4. **FAISS Vector Index** (optional, `rag_knowledge.faiss`)
   - Optimized semantic search index
   - Pre-computed normalized vectors for fast similarity search

## Quick Start

### Prerequisites

1. **Kaggle API Credentials**
   ```bash
   # Set up Kaggle API: https://www.kaggle.com/settings/account
   # Download your API token and place it at:
   # Windows: C:\Users\<username>\.kaggle\kaggle.json
   # Linux/Mac: ~/.kaggle/kaggle.json
   ```

2. **Install Dependencies**
   ```bash
   # Ensure you're in the capstone directory
   cd C:\Users\botboy\capstone

   # Install required packages
   pip install kagglehub faiss-cpu pypdf
   ```

### Run the Seed Script

**On Windows (PowerShell):**
```powershell
python seed_database.py
```

**On Windows (Bash/Git Bash):**
```bash
bash seed_database.sh
```

**On Linux/macOS:**
```bash
./seed_database.sh
```

This will:
1. Download CUAD contracts from Kaggle (Affiliate Agreements, Co-Branding, License Agreements - 10 total by default)
2. Extract and index contracts in the RAG database
3. Create web application database with sample tenant
4. Build FAISS vector index

### Custom Configuration

Download specific CUAD categories with custom limits:

```bash
python seed_database.py \
  --cuad-categories Service_Agreements License_Agreements \
  --cuad-limit 20
```

Use existing CUAD PDFs:

```bash
python seed_database.py \
  --cuad-dir ./my_contracts/
```

Custom database paths:

```bash
python seed_database.py \
  --web-db data/custom_web.sqlite3 \
  --rag-db data/custom_rag.sqlite3 \
  --faiss-index data/custom_vectors.faiss
```

## What Gets Seeded

### Capstone Organization
- **Organization ID:** `capstone`
- **Organization Name:** Capstone

### Admin User
- **Email:** admin@capstone.local
- **Password:** CapstoneAdmin!2026 (hashed)
- **Role:** Admin
- **Display Name:** Admin

These are the documented local development credentials from the README.

### CUAD Contracts
Real contracts from Kaggle's Atticus Open Contract Dataset:
- Default categories: Affiliate Agreements, Co-Branding, License Agreements
- Default limit: 10 contracts
- Extracted text indexed in RAG database for retrieval
- Linked to sample organization

### Procedural Knowledge Records (4)

1. **Contract Types** - Overview of common contract types and required/recommended fields
2. **NDA Best Practices** - Guidance for non-disclosure agreements
3. **License Clauses** - Software license key terms and considerations
4. **Payment Terms** - Standard payment term definitions and practices

## Database Schema

### Web Database Tables

```
organizations
├── id (PRIMARY KEY)
├── name (UNIQUE)
└── created_at

users
├── id (PRIMARY KEY)
├── email (UNIQUE)
├── password_hash
├── display_name
├── is_active
└── created_at

memberships
├── user_id (FOREIGN KEY → users.id)
├── organization_id (FOREIGN KEY → organizations.id)
└── role

contract_tenants
├── contract_id (PRIMARY KEY)
├── organization_id (FOREIGN KEY → organizations.id)
└── created_at

clause_templates
├── id (PRIMARY KEY)
├── organization_id (FOREIGN KEY → organizations.id)
├── name
├── clause_type
├── tags
├── status
└── ... (version tracking, timestamps)
```

### RAG Database Tables

```
rag_documents (SQLite standard table)
├── id (PRIMARY KEY)
├── dataset
├── knowledge_type
├── contract_type
├── text
├── metadata (JSON)
└── embedding (JSON)

rag_text (FTS5 virtual table for full-text search)
├── id
├── text
├── dataset
├── knowledge_type
└── contract_type
```

## Usage Examples

### Example 1: Full Seeding with CUAD and FAISS

```bash
python seed_database.py
```

Downloads 10 CUAD contracts from default categories and creates:
- `data/clm_web.sqlite3` (web app + CUAD contracts)
- `synthetic_data_loader/rag_knowledge.sqlite3` (CUAD + procedural knowledge)
- `synthetic_data_loader/rag_knowledge.faiss` (vector index)

### Example 2: Skip FAISS Index

```bash
python seed_database.py --skip-faiss
```

Useful if FAISS is not installed. FTS5 retrieval still works.

### Example 3: Use Existing CUAD PDFs

```bash
python seed_database.py --cuad-dir ./my_cuad_contracts/
```

Uses PDFs already downloaded to avoid re-downloading.

### Example 4: Download Different CUAD Categories

```bash
python seed_database.py \
  --cuad-categories Master_Service_Agreements Employment_Agreements \
  --cuad-limit 50
```

### Example 5: Web Database Only (No CUAD)

```bash
python seed_database.py --skip-cuad
```

Useful for testing web database without CUAD download dependencies.

### Example 6: Full Custom Setup

```bash
mkdir -p ./custom_data
python seed_database.py \
  --cuad-categories License_Agreements \
  --cuad-limit 25 \
  --web-db ./custom_data/web.db \
  --rag-db ./custom_data/rag.db \
  --faiss-index ./custom_data/vectors.faiss \
  --verbose
```

## Accessing the Seeded Database

### Login to Web Portal

```
URL: https://localhost:5173
Email: admin@capstone.local
Password: CapstoneAdmin!2026
Organization: Capstone
```

### Access CUAD Contracts Programmatically

```python
import sqlite3

conn = sqlite3.connect('data/clm_web.sqlite3')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# List all contracts for Capstone organization
cursor.execute(
    "SELECT * FROM contract_tenants WHERE organization_id = ?",
    ('capstone',)
)
contracts = cursor.fetchall()
for contract in contracts:
    print(f"Contract: {contract['contract_id']}")
```

### Search RAG Knowledge Base

```python
from agents.extraction_agent.hybrid_rag import retrieve

# Semantic search for contract guidance
result = retrieve(
    "software development service agreement",
    "synthetic_data_loader/rag_knowledge.sqlite3"
)
if result:
    print(f"Retrieved: {result['name']}")
    print(f"Score: {result['score']}")
    print(f"Type: {result['contract_type']}")
```

## Troubleshooting

### Issue: "No module named 'web.clm_web'"

**Solution:** Ensure you're running from the capstone directory:
```bash
cd C:\Users\botboy\capstone
python seed_database.py
```

### Issue: Kaggle API Error or "Dataset not found"

**Solution:**
1. Install Kaggle API: `pip install kagglehub`
2. Set up credentials: https://www.kaggle.com/settings/account
3. Download token and place at:
   - Windows: `C:\Users\<username>\.kaggle\kaggle.json`
   - Linux/Mac: `~/.kaggle/kaggle.json`
4. Or skip CUAD and use web-only seeding:
   ```bash
   python seed_database.py --skip-cuad
   ```

### Issue: "FAISS is not installed"

**Solution:** Install it with:
```bash
pip install faiss-cpu
```

Or skip FAISS:
```bash
python seed_database.py --skip-faiss
```

### Issue: PDF Extraction Failing

**Solution:**
1. Ensure pypdf is installed: `pip install pypdf`
2. Check that PDF files are valid: `file *.pdf`
3. Use `--skip-cuad` if extraction is problematic:
   ```bash
   python seed_database.py --skip-cuad
   ```

### Issue: Database already exists

The script checks if databases are already seeded and skips re-seeding. To clear and re-seed:

**Windows:**
```powershell
rm data/clm_web.sqlite3, synthetic_data_loader/rag_knowledge.sqlite3, synthetic_data_loader/rag_knowledge.faiss -ErrorAction SilentlyContinue
rm -r synthetic_data_loader/data/cuad_subset -ErrorAction SilentlyContinue
python seed_database.py
```

**Linux/Mac:**
```bash
rm -f data/clm_web.sqlite3 synthetic_data_loader/rag_knowledge.sqlite3 synthetic_data_loader/rag_knowledge.faiss
rm -rf synthetic_data_loader/data/cuad_subset
python seed_database.py
```

**Note**: The CUAD PDF files are downloaded fresh each time during seeding. The `synthetic_data_loader/data/` directory is gitignored and safe to delete between runs.

### Issue: Out of Memory During CUAD Download

**Solution:**
1. Reduce the limit: `python seed_database.py --cuad-limit 5`
2. Or download specific categories: `python seed_database.py --cuad-categories Service_Agreements --cuad-limit 10`
3. The full CUAD dataset is ~107MB, but processed incrementally

### Issue: "Foreign key constraint failed"

This shouldn't happen with the seed script, but if it does, ensure:
1. You're using the latest database schema
2. You haven't manually modified foreign key constraints
3. Run `python -c "from web.clm_web.db import WebDatabase; WebDatabase('data/clm_web.sqlite3')"` to reinitialize

### Issue: Verbose Logging

Enable debug output:
```bash
python seed_database.py --verbose
```

This helps diagnose CUAD download, PDF extraction, and RAG indexing issues.

## Extending the Seed Data

The seed script automatically downloads CUAD contracts. To customize:

### Download Additional CUAD Categories

See all available CUAD categories by downloading with `--verbose`:

```bash
python seed_database.py \
  --cuad-categories Master_Service_Agreements Employment_Agreements \
  --cuad-limit 50 \
  --verbose
```

Available categories include:
- Affiliate_Agreements
- Co_Branding
- License_Agreements
- Master_Service_Agreements
- Service_Agreements
- Employment_Agreements
- And ~50+ more from Kaggle CUAD

### Add Custom Local Contracts

Place PDF files in a directory and seed them:

```bash
# Copy your PDFs
mkdir my_contracts
cp /path/to/*.pdf my_contracts/

# Seed with existing PDFs
python seed_database.py \
  --cuad-dir ./my_contracts/ \
  --skip-cuad  # Skip Kaggle download
```

### Add a New Procedural Knowledge Record

Edit `SAMPLE_RAG_KNOWLEDGE` in `seed_database.py`:

```python
SAMPLE_RAG_KNOWLEDGE.append({
    "id": "knowledge:your_topic",
    "name": "Your Topic Name",
    "knowledge_type": "contract_profile",  # or "procedural"
    "contract_type": "contract_type",
    "dataset": "internal",
    "text": "Full knowledge text...",
    "required_fields": ["field1", "field2"],
    "recommended_fields": ["field3", "field4"],
    "guidance": "Practical guidance..."
})
```

Then re-run:
```bash
python seed_database.py
```

## Environment Variables

The seed script respects these environment variables:

- `EXTRACTION_RAG_DB`: Override RAG database path
- `EXTRACTION_RAG_FAISS_INDEX`: Override FAISS index path
- `EXTRACTION_RAG_ENABLED`: Set to "1" to enable RAG in the application

## Next Steps

1. Start the web server:
   ```bash
   python -m web.clm_web.server
   ```

2. Start the extraction agent:
   ```bash
   python -m agents.extraction_agent.pipeline
   ```

3. Access the application (check server output for URL)

## Support

For issues or questions, check:
- [Architecture Documentation](docs/README.md)
- [Troubleshooting Guide](agents/extraction_agent/docs/troubleshooting.md)
- [Repository README](README.md)
