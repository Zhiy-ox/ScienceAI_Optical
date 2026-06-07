"""Shared pytest configuration for local and CI test runs."""

from __future__ import annotations

import importlib.util
import pytest

_HAS_PYTEST_ASYNCIO = importlib.util.find_spec("pytest_asyncio") is not None


def pytest_addoption(parser: pytest.Parser) -> None:
    """Define pytest-asyncio's ini option when that plugin is unavailable.

    The project declares pytest-asyncio in its dev extras, but some local review
    environments only have AnyIO installed through FastAPI. Defining the option
    here prevents an unknown-config warning in those minimal environments.
    """
    if not _HAS_PYTEST_ASYNCIO:
        parser.addini("asyncio_mode", "Fallback asyncio mode setting", default="auto")


@pytest.fixture
def anyio_backend() -> str:
    """Run AnyIO-backed async tests on asyncio only.

    This prevents AnyIO from parametrizing tests over Trio, which this project
    does not depend on.
    """
    return "asyncio"


def pytest_configure(config: pytest.Config) -> None:
    """Register local fallback markers when optional test plugins are unavailable."""
    if not _HAS_PYTEST_ASYNCIO:
        config.addinivalue_line("markers", "asyncio: run async tests with AnyIO fallback")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Adapt async tests for minimal local environments.

    CI/dev environments with pytest-asyncio installed continue to run the full test suite
    normally. In minimal local environments, AnyIO runs async tests.
    """
    anyio_marker = pytest.mark.anyio
    for item in items:
        if not _HAS_PYTEST_ASYNCIO and item.get_closest_marker("asyncio") is not None:
            item.add_marker(anyio_marker)
