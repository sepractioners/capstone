"""Main setup orchestration module."""

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # Python <3.11


PROJECT_ROOT = Path(__file__).parent.parent.parent
SYSTEM_REQS_FILE = PROJECT_ROOT / "system-requirements.toml"


class Color:
    """ANSI color codes."""

    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"

    @classmethod
    def step(cls, msg: str) -> str:
        return f"{cls.BLUE}==> {msg}{cls.RESET}"

    @classmethod
    def ok(cls, msg: str) -> str:
        return f"{cls.GREEN}✓ {msg}{cls.RESET}"

    @classmethod
    def warn(cls, msg: str) -> str:
        return f"{cls.YELLOW}⚠ {msg}{cls.RESET}"

    @classmethod
    def error(cls, msg: str) -> str:
        return f"{cls.RED}✗ {msg}{cls.RESET}"


def load_system_requirements() -> Dict:
    """Load system-requirements.toml."""
    if not SYSTEM_REQS_FILE.exists():
        raise FileNotFoundError(f"system-requirements.toml not found at {SYSTEM_REQS_FILE}")

    with open(SYSTEM_REQS_FILE, "rb") as f:
        return tomllib.load(f)


def get_platform_name() -> str:
    """Return 'macos', 'linux', or 'windows'."""
    system = platform.system()
    if system == "Darwin":
        return "macos"
    elif system == "Linux":
        return "linux"
    elif system == "Windows":
        return "windows"
    else:
        raise ValueError(f"Unsupported OS: {system}")


def run_command(cmd: str, shell: bool = True) -> Optional[str]:
    """Run a shell command, return output or None if failed."""
    try:
        result = subprocess.run(
            cmd, shell=shell, capture_output=True, text=True, timeout=30
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def check_command_exists(cmd: str) -> bool:
    """Check if a command exists in PATH."""
    which_cmd = "where" if get_platform_name() == "windows" else "which"
    result = subprocess.run(
        f"{which_cmd} {cmd}", shell=True, capture_output=True, timeout=5
    )
    return result.returncode == 0


def check_version(current: str, required: str) -> bool:
    """Simple version comparison (assumes semantic versioning)."""
    # Simplified: just extract major.minor for comparison
    # In production, use packaging.version.parse
    try:
        current_parts = [int(x) for x in current.split(".")[:2]]
        required_parts = [int(x.lstrip(">=<")) for x in required.split(".")[:2]]
        return current_parts >= required_parts
    except (ValueError, IndexError):
        return True  # Assume ok if we can't parse


def validate_system_requirements(platform_name: str, verbose: bool = True) -> bool:
    """Validate that all required system tools are installed."""
    config = load_system_requirements()
    print(Color.step(f"Validating system requirements for {platform_name}"))

    all_ok = True
    for tool_name, tool_spec in config.get("required", {}).items():
        version = tool_spec.get("version", "any")
        note = tool_spec.get("note", "")

        if check_command_exists(tool_name):
            version_output = run_command(f"{tool_name} --version")
            if version_output and verbose:
                print(
                    Color.ok(f"{tool_name} {version_output.split()[0] if version_output else 'found'}")
                )
        else:
            all_ok = False
            install_cmd = tool_spec.get("install", {}).get(platform_name, "see SETUP.md")
            print(Color.error(f"{tool_name} not found (required: {version})"))
            print(f"    {note}")
            print(f"    Install: {install_cmd}")

    # Check dev tools
    for tool_name, tool_spec in config.get("dev-tools", {}).items():
        if check_command_exists(tool_name):
            version_output = run_command(f"{tool_name} --version")
            if verbose:
                print(Color.ok(f"{tool_name} {version_output.split()[0] if version_output else 'found'}"))
        else:
            print(Color.warn(f"dev-tool {tool_name} not installed (optional)"))

    return all_ok


def setup_venv() -> bool:
    """Create Python virtual environment using uv."""
    print(Color.step("Setting up Python virtual environment"))

    venv_path = PROJECT_ROOT / ".venv"
    if venv_path.exists():
        print(Color.ok("Virtual environment already exists"))
        return True

    try:
        result = subprocess.run(
            "uv venv", cwd=PROJECT_ROOT, shell=True, timeout=60
        )
        if result.returncode == 0:
            print(Color.ok("Virtual environment created"))
            return True
        else:
            print(Color.error("Failed to create virtual environment"))
            return False
    except Exception as e:
        print(Color.error(f"Error creating venv: {e}"))
        return False


def sync_dependencies(all_groups: bool = False) -> bool:
    """Install Python dependencies using uv."""
    print(Color.step("Installing Python dependencies"))

    cmd = "uv sync"
    if all_groups:
        cmd += " --all-groups"

    try:
        result = subprocess.run(
            cmd, cwd=PROJECT_ROOT, shell=True, timeout=300
        )
        if result.returncode == 0:
            print(Color.ok("Dependencies synced"))
            return True
        else:
            print(Color.error("Failed to sync dependencies"))
            return False
    except Exception as e:
        print(Color.error(f"Error syncing dependencies: {e}"))
        return False


def init_database() -> bool:
    """Initialize SQLite database."""
    print(Color.step("Initializing SQLite database"))

    try:
        result = subprocess.run(
            "uv run python -m web.clm_web.db --init",
            cwd=PROJECT_ROOT,
            shell=True,
            timeout=30,
        )
        if result.returncode == 0:
            print(Color.ok("Database initialized"))
            return True
        else:
            print(Color.error("Failed to initialize database"))
            return False
    except Exception as e:
        print(Color.error(f"Error initializing database: {e}"))
        return False


def generate_tls_certs() -> bool:
    """Generate HTTPS certificates using mkcert."""
    print(Color.step("Generating HTTPS certificates"))

    certs_dir = PROJECT_ROOT / ".certs"
    if certs_dir.exists():
        print(Color.ok("Certificates already exist"))
        return True

    try:
        certs_dir.mkdir(parents=True, exist_ok=True)

        # Generate certificate
        result = subprocess.run(
            f"mkcert -cert-file .certs/localhost.pem -key-file .certs/localhost-key.pem "
            "localhost 127.0.0.1 ::1",
            cwd=PROJECT_ROOT,
            shell=True,
            timeout=30,
        )

        if result.returncode == 0:
            print(Color.ok("HTTPS certificates generated"))
            return True
        else:
            print(Color.error("Failed to generate certificates"))
            return False
    except Exception as e:
        print(Color.error(f"Error generating certificates: {e}"))
        return False


def download_sample_data() -> bool:
    """Download CUAD sample contracts."""
    print(Color.step("Downloading sample contracts (CUAD subset)"))

    data_dir = PROJECT_ROOT / "synthetic_data_loader" / "data"
    manifest = data_dir / "cuad_subset_manifest.txt"

    if manifest.exists():
        print(Color.ok("Sample contracts already downloaded"))
        return True

    try:
        data_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            "uv run python -m synthetic_data_loader.download_cuad_subset",
            cwd=PROJECT_ROOT,
            shell=True,
            timeout=600,  # 10 minutes
        )

        if result.returncode == 0:
            print(Color.ok("Sample contracts downloaded"))
            return True
        else:
            print(Color.error("Failed to download sample contracts"))
            return False
    except Exception as e:
        print(Color.error(f"Error downloading sample data: {e}"))
        return False


def build_rag_index() -> bool:
    """Build RAG knowledge index."""
    print(Color.step("Building RAG knowledge index"))

    rag_db = PROJECT_ROOT / "synthetic_data_loader" / "rag_knowledge.sqlite3"
    if rag_db.exists():
        print(Color.ok("RAG index already exists"))
        return True

    try:
        result = subprocess.run(
            "uv run python -m extraction_agent.build_rag_index",
            cwd=PROJECT_ROOT,
            shell=True,
            timeout=300,
        )

        if result.returncode == 0:
            print(Color.ok("RAG index built"))
            return True
        else:
            print(Color.error("Failed to build RAG index"))
            return False
    except Exception as e:
        print(Color.error(f"Error building RAG index: {e}"))
        return False


def install_frontend_deps() -> bool:
    """Install frontend dependencies with bun."""
    print(Color.step("Installing frontend dependencies"))

    if not check_command_exists("bun"):
        print(Color.warn("bun not found - skipping frontend setup"))
        print("    Install with: npm install -g bun")
        return True

    try:
        frontend_dir = PROJECT_ROOT / "web" / "frontend"
        result = subprocess.run(
            "bun install", cwd=frontend_dir, shell=True, timeout=300
        )

        if result.returncode == 0:
            print(Color.ok("Frontend dependencies installed"))
            return True
        else:
            print(Color.error("Failed to install frontend dependencies"))
            return False
    except Exception as e:
        print(Color.error(f"Error installing frontend deps: {e}"))
        return False


def create_env_file() -> bool:
    """Create .env file from .env.example if it doesn't exist."""
    env_file = PROJECT_ROOT / ".env"
    env_example = PROJECT_ROOT / ".env.example"

    if env_file.exists():
        print(Color.ok(".env already exists"))
        return True

    if not env_example.exists():
        print(Color.warn(".env.example not found - skipping .env creation"))
        return False

    try:
        env_file.write_text(env_example.read_text())
        print(Color.ok(".env created from .env.example"))
        return True
    except Exception as e:
        print(Color.error(f"Error creating .env: {e}"))
        return False


def main() -> int:
    """Main setup orchestration."""
    parser = argparse.ArgumentParser(
        description="Capstone project setup orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m tools.setup --validate-only
  python -m tools.setup --no-ollama
  python -m tools.setup --all
        """,
    )

    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate system requirements, don't install anything",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run complete setup including sample data and RAG index",
    )
    parser.add_argument(
        "--no-sample-data",
        action="store_true",
        help="Skip downloading sample contracts",
    )
    parser.add_argument(
        "--skip-rag",
        action="store_true",
        help="Skip building RAG index",
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip frontend dependency installation",
    )
    parser.add_argument(
        "--platform",
        choices=["macos", "linux", "windows"],
        help="Force platform (default: detect)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    platform_name = args.platform or get_platform_name()
    print(f"\nCapstone Setup\n{'=' * 50}")
    print(f"Platform: {platform_name}")
    print(f"Project: {PROJECT_ROOT}\n")

    # Step 1: Validate system requirements
    if not validate_system_requirements(platform_name, verbose=args.verbose):
        if not args.validate_only:
            print(Color.error("\nPlease install missing system dependencies and try again."))
            return 1

    if args.validate_only:
        print(Color.ok("\nAll system requirements met!"))
        return 0

    # Step 2: Setup Python environment
    if not setup_venv():
        return 1

    # Step 3: Sync dependencies
    if not sync_dependencies(all_groups=args.all):
        return 1

    # Step 4: Create .env
    if not create_env_file():
        print(Color.warn("Skipping .env creation (use .env.example as reference)"))
        # Not fatal

    # Step 5: Initialize database
    if not init_database():
        return 1

    # Step 6: Generate TLS certificates
    if not generate_tls_certs():
        print(Color.warn("TLS certificate generation failed - you may have issues with HTTPS"))
        # Not fatal

    # Step 7-9: Optional features
    if args.all:
        if not args.no_sample_data:
            download_sample_data()

        if not args.skip_rag:
            build_rag_index()

    # Step 10: Frontend
    if not args.skip_frontend:
        install_frontend_deps()

    # Done
    print(f"\n{'=' * 50}")
    print(Color.ok("Setup complete!"))
    print(f"""
Next steps:

1. Start Ollama (if using local LLM):
   ollama serve

2. Start all services:
   python -m tools.setup start
   OR
   bash scripts/run-mac.sh  (macOS/Linux)
   powershell scripts/run-all.ps1  (Windows)

3. Access the platform:
   Contract Portal:  https://localhost:5173
   Agent Console:    https://localhost:5174
   API:              https://localhost:8443

4. Login with:
   Email:    admin@capstone.local
   Password: CapstoneAdmin!2026
    """)

    return 0


if __name__ == "__main__":
    sys.exit(main())
