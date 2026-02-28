#!/usr/bin/env python3
"""Export partner data to Arize AX.

Usage:
    python scripts/export_partner_to_arize.py partner_data/pg/data/v1_2026-02-27.json
"""

import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "copilot-insights-bridge"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "copilot-insights-bridge" / ".env")

from src.config import BridgeSettings
from src.extraction.models import AppInsightsEvent
from src.reconstruction.tree_builder import TraceTreeBuilder
from src.transformation.mapper import OpenInferenceMapper
from src.export.otel_exporter import create_tracer_provider, shutdown_tracer_provider
from src.export.span_builder import SpanBuilder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/export_partner_to_arize.py <partner_data.json>")
        sys.exit(1)

    data_file = Path(sys.argv[1])
    if not data_file.exists():
        print(f"Error: File not found: {data_file}")
        sys.exit(1)

    # Load settings from .env
    settings = BridgeSettings()  # type: ignore[call-arg]

    # Load & parse events (raw JSON array format)
    with open(data_file) as f:
        rows = json.load(f)

    logger.info("Loaded %d events from %s", len(rows), data_file.name)

    events = [AppInsightsEvent.from_query_row(r) for r in rows]
    logger.info("Parsed %d events", len(events))

    # Build trace trees
    builder = TraceTreeBuilder()
    trees = builder.build_trees(events)
    logger.info("Built %d trace trees", len(trees))

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
                flags.append(f"system_topics={len(sys_topics)}")
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

    logger.info("=" * 70)
    logger.info("✅ Export Complete!")
    logger.info("=" * 70)
    logger.info("Exported %d traces to Arize project '%s'", exported, settings.arize_project_name)
    logger.info("")
    logger.info("Next steps:")
    logger.info("1. Visit Arize UI: https://app.arize.com")
    logger.info("2. Navigate to project: %s", settings.arize_project_name)
    logger.info("3. Verify traces and metadata are visible")
    logger.info("")


if __name__ == "__main__":
    main()
