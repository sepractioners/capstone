"""
Capstone project setup orchestrator.

Cross-platform setup that reads from system-requirements.toml and manages:
- System dependency validation
- Python virtual environment creation
- Database initialization
- HTTPS certificate generation
- Optional: sample data download, RAG index building, Ollama setup, frontend deps

Usage:
    python -m tools.setup --help
    python -m tools.setup --validate-only
    python -m tools.setup --platform macos --no-ollama --skip-sample-data
    python -m tools.setup --all
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.setup.main import main

if __name__ == "__main__":
    sys.exit(main())
