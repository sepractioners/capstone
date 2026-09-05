"""HTTPS/HTTP2 local server entry point."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from hypercorn.asyncio import serve
from hypercorn.config import Config

from .api import app


def main() -> None:
    """Serve the API over local TLS with Hypercorn HTTP/2 support."""
    config = Config()
    config.bind = [os.environ.get("CLM_BIND", "localhost:8443")]
    config.certfile = os.environ.get("CLM_CERTFILE", str(Path(".certs/localhost.pem")))
    config.keyfile = os.environ.get("CLM_KEYFILE", str(Path(".certs/localhost-key.pem")))
    config.alpn_protocols = ["h2", "http/1.1"]
    asyncio.run(serve(app, config))


if __name__ == "__main__":
    main()
