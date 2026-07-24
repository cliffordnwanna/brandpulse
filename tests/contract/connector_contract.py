"""Shared connector contract test suite (Engineering Design §20).

Every connector must pass these checks before being merged. Not a pytest
module itself (no ``test_`` prefix) — a mixin base class that per-connector
contract test modules subclass, supplying a connector fixture and one sample
raw item via ``make_connector()``/``make_raw_item()``. This is the first time
this shared suite exists (flagged as possibly missing in Milestone 3's
acceptance criteria) — it was built here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from brandpulse.connectors.base import BaseConnector, HealthStatus, RunResult
from brandpulse.schema import Mention


class ConnectorContractTests(ABC):
    """Subclass this per connector, implementing the two fixtures below.

    Both fixtures are plain methods (not pytest fixtures) so subclasses can
    freely use pytest fixtures like ``tmp_path``/``monkeypatch`` as ordinary
    test-method parameters without fighting this class's abstraction.
    """

    @abstractmethod
    def make_connector(self) -> BaseConnector:
        """Return a connector instance configured for contract testing."""
        raise NotImplementedError

    @abstractmethod
    def make_raw_item(self) -> Any:
        """Return one source-native raw item suitable for ``normalize()``."""
        raise NotImplementedError

    def test_search_returns_valid_run_result(self):
        connector = self.make_connector()
        result = connector.search(
            ["test"], datetime(2020, 1, 1, tzinfo=UTC), datetime(2030, 1, 1, tzinfo=UTC)
        )
        assert isinstance(result, RunResult)

    def test_normalize_output_matches_canonical_schema(self):
        connector = self.make_connector()
        raw_item = self.make_raw_item()
        mention = connector.normalize(raw_item)
        assert isinstance(mention, Mention)
        assert mention.connector_version == connector.version
        assert mention.reliability == connector.reliability

    def test_validate_rejects_malformed_input(self):
        connector = self.make_connector()
        raw_item = self.make_raw_item()
        mention = connector.normalize(raw_item)
        malformed = mention.model_copy(update={"text": ""})
        assert connector.validate(malformed) is False

    def test_validate_accepts_well_formed_input(self):
        connector = self.make_connector()
        mention = connector.normalize(self.make_raw_item())
        assert connector.validate(mention) is True

    def test_health_responds(self):
        connector = self.make_connector()
        status = connector.health()
        assert isinstance(status, HealthStatus)
        assert isinstance(status.healthy, bool)
