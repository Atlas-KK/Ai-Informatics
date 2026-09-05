"""Local-only application entry point."""

import uvicorn

from ai_intel.api.app import create_app
from ai_intel.config import Settings


def run() -> None:
    """Run the local API without exposing it to the network."""

    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
