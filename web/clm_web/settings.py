"""Environment-backed web application settings."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: str = os.environ.get("CLM_DATABASE_PATH", "clm.sqlite3")
    jwt_secret: str = os.environ.get(
        "CLM_JWT_SECRET", "development-only-change-this-secret-before-deployment-123456"
    )
    issuer: str = os.environ.get("CLM_ISSUER", "https://localhost:8443")
    access_token_seconds: int = int(os.environ.get("CLM_ACCESS_TOKEN_SECONDS", "900"))
    frontend_dist: str = os.environ.get(
        "CLM_FRONTEND_DIST", str(Path(__file__).parent.parent / "frontend" / "dist")
    )


settings = Settings()
