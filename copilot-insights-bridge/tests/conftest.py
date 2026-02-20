"""Shared test fixtures for the copilot-insights-bridge test suite."""

import json
from pathlib import Path

import pytest

from src.extraction.models import AppInsightsEvent

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> list[dict]:
    """Load and parse a JSON fixture file."""
    return json.loads((FIXTURES_DIR / name).read_text())


def _parse_events(rows: list[dict]) -> list[AppInsightsEvent]:
    """Parse raw fixture rows into AppInsightsEvent objects."""
    return [AppInsightsEvent.from_query_row(row) for row in rows]


def load_real_data_table(name: str = "real_data_dump.json") -> list[dict]:
    """Load real App Insights table-format data and convert to row dicts.

    The real data dump uses the Azure table format::

        {"tables": [{"columns": [...], "rows": [[...], ...]}]}

    This function converts each row array into a dict keyed by column names.
    """
    raw = json.loads((FIXTURES_DIR / name).read_text())
    table = raw["tables"][0]
    columns = [col["name"] for col in table["columns"]]
    return [dict(zip(columns, row)) for row in table["rows"]]


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def single_conversation_raw() -> list[dict]:
    return _load_fixture("single_conversation.json")


@pytest.fixture
def single_conversation_events(single_conversation_raw: list[dict]) -> list[AppInsightsEvent]:
    return _parse_events(single_conversation_raw)


@pytest.fixture
def multi_topic_raw() -> list[dict]:
    return _load_fixture("multi_topic_conversation.json")


@pytest.fixture
def multi_topic_events(multi_topic_raw: list[dict]) -> list[AppInsightsEvent]:
    return _parse_events(multi_topic_raw)


@pytest.fixture
def generative_raw() -> list[dict]:
    return _load_fixture("generative_answers.json")


@pytest.fixture
def generative_events(generative_raw: list[dict]) -> list[AppInsightsEvent]:
    return _parse_events(generative_raw)


@pytest.fixture
def error_raw() -> list[dict]:
    return _load_fixture("error_conversation.json")


@pytest.fixture
def error_events(error_raw: list[dict]) -> list[AppInsightsEvent]:
    return _parse_events(error_raw)


@pytest.fixture
def real_data_rows() -> list[dict]:
    """Parsed real data dump rows (table format → list of dicts)."""
    return load_real_data_table()


@pytest.fixture
def real_data_events(real_data_rows: list[dict]) -> list[AppInsightsEvent]:
    """Parsed real data dump as AppInsightsEvent objects."""
    return _parse_events(real_data_rows)
