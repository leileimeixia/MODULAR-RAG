"""Smoke tests for the stage A project skeleton."""


def test_top_level_packages_importable() -> None:
    import core
    import ingestion
    import libs
    import mcp_server
    import observability

    assert core is not None
    assert ingestion is not None
    assert libs is not None
    assert mcp_server is not None
    assert observability is not None


def test_key_placeholder_modules_importable() -> None:
    import core.settings
    import ingestion.pipeline
    import libs.llm.llm_factory
    import mcp_server.server
    import observability.logger

    assert core.settings is not None
    assert ingestion.pipeline is not None
    assert libs.llm.llm_factory is not None
    assert mcp_server.server is not None
    assert observability.logger is not None
