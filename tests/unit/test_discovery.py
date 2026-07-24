"""Unit tests for connector plugin auto-discovery (Engineering Design §3)."""

from brandpulse.connectors import discover_connectors
from tests.fixtures import stub_connectors
from tests.fixtures.stub_connectors.stub_connector import StubConnector


def test_discover_connectors_finds_stub_with_zero_manual_registration():
    discovered = discover_connectors(package=stub_connectors)

    assert discovered == {"stub_source": StubConnector}


def test_discover_connectors_skips_abstract_base():
    discovered = discover_connectors(package=stub_connectors)

    assert "BaseConnector" not in discovered
