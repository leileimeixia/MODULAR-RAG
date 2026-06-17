"""Entry point for the Modular RAG MCP Server."""

from __future__ import annotations

from core.settings import SettingsError, load_settings
from observability.logger import get_logger


def main() -> int:
    """Load settings and run the server entry point placeholder."""
    logger = get_logger(__name__)
    try:
        settings = load_settings()
    except SettingsError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    logger.info(
        "Config OK: LLM=%s/%s, Embed=%s/%s",
        settings.llm.provider,
        settings.llm.model,
        settings.embedding.provider,
        settings.embedding.model,
    )
    print("Modular RAG MCP Server configuration loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
