#!/usr/bin/env python3
"""Export a data dump through the full pipeline to Arize AX.

Usage:
    python scripts/export_to_arize.py                      # uses live_data_dump.json
    python scripts/export_to_arize.py real_data_dump.json   # uses a specific fixture
    python scripts/export_to_arize.py --shift-to-now        # shift timestamps to now
"""

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.config import BridgeSettings
from src.extraction.models import AppInsightsEvent
from src.reconstruction.span_models import SpanNode
from src.reconstruction.tree_builder import TraceTreeBuilder
from src.transformation.mapper import OpenInferenceMapper
from src.export.otel_exporter import create_tracer_provider, shutdown_tracer_provider
from src.export.span_builder import SpanBuilder
from tests.conftest import load_real_data_table

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _shift_tree_timestamps(node: "SpanNode", offset: timedelta) -> None:
    """Recursively shift all start/end times in a span tree by *offset*."""
    node.start_time = node.start_time + offset
    node.end_time = node.end_time + offset
    for child in node.children:
        _shift_tree_timestamps(child, offset)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    fixture_name = args[0] if args else "live_data_dump.json"
    shift_to_now = "--shift-to-now" in flags

    # Load settings from .env
    settings = BridgeSettings()  # type: ignore[call-arg]

    # Load & parse events
    rows = load_real_data_table(fixture_name)
    events = [AppInsightsEvent.from_query_row(r) for r in rows]
    logger.info("Loaded %d events from %s", len(events), fixture_name)

    # Build trace trees
    builder = TraceTreeBuilder()
    trees = builder.build_trees(events)
    logger.info("Built %d trace trees", len(trees))

    # Optionally shift timestamps to current time (for historical data re-export)
    if shift_to_now and trees:
        latest_end = max(root.end_time for root in trees)
        now = datetime.now(timezone.utc)
        offset = now - latest_end
        logger.info("Shifting timestamps forward by %s (latest span end → now)", offset)
        for root in trees:
            _shift_tree_timestamps(root, offset)

    # Set up Arize OTLP exporter
    provider = create_tracer_provider(
        space_id=settings.arize_space_id,
        api_key=settings.arize_api_key,
        project_name=settings.arize_project_name,
    )
    tracer = provider.get_tracer("copilot-bridge")
    span_builder = SpanBuilder(tracer)
    mapper = OpenInferenceMapper()

    # Export each tree
    exported = 0
    for root in trees:
        try:
            span_builder.export_trace_tree(root, attributes_map=mapper.map_attributes)
            exported += 1

            # Summary line per trace
            flags = []
            if root.knowledge_search_detected:
                flags.append("knowledge_search")
            sys_topics = [c.name for c in root.children if c.is_system_topic]
            if sys_topics:
                flags.append(f"system_topics={sys_topics}")
            if root.locale:
                flags.append(f"locale={root.locale}")

            input_preview = root.input_messages[0][:50] if root.input_messages else "(no input)"
            flag_str = f"  [{', '.join(flags)}]" if flags else ""
            logger.info(
                "  Trace %d/%d: %s%s",
                exported, len(trees), input_preview, flag_str,
            )
        except Exception:
            logger.exception("Failed to export tree: %s", root.name)

    # Flush and shutdown
    logger.info("Flushing spans to Arize...")
    provider.force_flush()
    shutdown_tracer_provider(provider)
    logger.info("Done. Exported %d traces to Arize project '%s'", exported, settings.arize_project_name)


if __name__ == "__main__":
    main()
