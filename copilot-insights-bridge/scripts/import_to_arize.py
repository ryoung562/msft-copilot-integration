#!/usr/bin/env python3
"""Universal file import for Copilot Studio telemetry.

Loads one or more JSON files (any supported format), reconstructs trace
trees, and optionally exports them to Arize AX.

Usage:
    python scripts/import_to_arize.py data.json                          # inspect (default)
    python scripts/import_to_arize.py data.json --export                 # export to Arize
    python scripts/import_to_arize.py data.json --export --shift-to-now  # with timestamp shift
    python scripts/import_to_arize.py *.json --export                    # multiple files
    python scripts/import_to_arize.py data.json --stats                  # statistics only
    python scripts/import_to_arize.py data.json --diagnose               # gap analysis only
"""

import argparse
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extraction.loader import load_events_from_file
from src.extraction.models import AppInsightsEvent
from src.reconstruction.tree_builder import TraceTreeBuilder, shift_tree_timestamps
from src.transformation.mapper import OpenInferenceMapper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import Copilot Studio telemetry files to Arize AX.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
    %(prog)s data.json                          # inspect (stats + diagnose)
    %(prog)s data.json --export                 # export to Arize
    %(prog)s data.json --export --shift-to-now  # shift timestamps to now
    %(prog)s *.json --export                    # multiple files
    %(prog)s data.json --stats                  # statistics only
    %(prog)s data.json --diagnose               # gap analysis only
""",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="One or more JSON data files to process",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Push traces to Arize AX (requires BRIDGE_* env vars)",
    )
    parser.add_argument(
        "--shift-to-now",
        action="store_true",
        help="Shift all timestamps so the latest span ends at current time",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show event statistics (counts, time range, channels, topics)",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Run trace reconstruction and report gap analysis",
    )
    parser.add_argument(
        "--include-design-mode",
        action="store_true",
        help="Include design-mode (test canvas) traffic (default: exclude)",
    )
    return parser


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def show_statistics(events: list[AppInsightsEvent]) -> None:
    """Display statistics about the loaded data."""
    print("\n" + "=" * 70)
    print("DATA STATISTICS")
    print("=" * 70)

    print(f"\nTotal events: {len(events)}")

    if not events:
        return

    start = min(e.timestamp for e in events)
    end = max(e.timestamp for e in events)
    print(f"Time range: {start} to {end}")
    print(f"Duration: {end - start}")

    # Event types
    print("\nEvent types:")
    for name, count in Counter(e.name for e in events).most_common():
        print(f"  {name}: {count}")

    # Conversations
    conv_ids = {e.conversation_id for e in events if e.conversation_id}
    print(f"\nUnique conversations: {len(conv_ids)}")

    # Sessions
    session_ids = {e.session_id for e in events if e.session_id}
    print(f"Unique sessions: {len(session_ids)}")

    # Channels
    channels = {e.channel_id for e in events if e.channel_id}
    print(f"Channels: {', '.join(sorted(channels)) if channels else 'None'}")

    # Design mode
    design_mode_events = sum(1 for e in events if e.design_mode == "True")
    prod_events = len(events) - design_mode_events
    print(f"\nDesign mode events: {design_mode_events}")
    print(f"Production events: {prod_events}")

    # Topics
    topics = {e.topic_name for e in events if e.topic_name}
    print(f"\nUnique topics: {len(topics)}")
    if topics:
        print("Topics:")
        for topic in sorted(topics):
            print(f"  - {topic}")

    # Agent types
    agent_types = {e.agent_type for e in events if e.agent_type}
    if agent_types:
        print(f"\nAgent types: {', '.join(sorted(agent_types))}")

    # Locales
    locales = {e.locale for e in events if e.locale}
    if locales:
        print(f"Locales: {', '.join(sorted(locales))}")

    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def run_diagnostics(events: list[AppInsightsEvent]) -> None:
    """Run gap analysis diagnostics on the data."""
    print("\n" + "=" * 70)
    print("GAP ANALYSIS DIAGNOSTICS")
    print("=" * 70 + "\n")

    builder = TraceTreeBuilder()
    trees = builder.build_trees(events)
    print(f"Built {len(trees)} trace trees\n")

    # Count features detected
    knowledge_search_count = sum(1 for t in trees if t.knowledge_search_detected)
    system_topic_count = sum(
        1 for t in trees
        for child in t.children
        if hasattr(child, "is_system_topic") and child.is_system_topic
    )

    print(f"Knowledge search detected: {knowledge_search_count} traces")
    print(f"System topics detected: {system_topic_count} spans")

    # Locale detection
    locales_in_trees = {t.locale for t in trees if t.locale}
    if locales_in_trees:
        print(f"Locales detected: {', '.join(sorted(locales_in_trees))}")

    # Empty traces
    empty_count = sum(
        1 for t in trees
        if not t.input_messages and not t.output_messages and not t.children
    )
    if empty_count:
        print(f"\nEmpty traces (would be filtered): {empty_count}")

    # Show sample tree structure
    if trees:
        print("\nSample trace structure:")
        sample = trees[0]
        print(f"  Root: {sample.name} ({sample.span_kind.value})")
        print(f"    Input: {len(sample.input_messages)} messages")
        print(f"    Output: {len(sample.output_messages)} messages")
        print(f"    Children: {len(sample.children)}")
        for child in sample.children[:3]:
            print(f"      - {child.name} ({child.span_kind.value})")
            if child.children:
                print(f"        Grandchildren: {len(child.children)}")

    print("\n" + "=" * 70 + "\n")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_trees(trees: list, shift_to_now: bool) -> None:
    """Export trace trees to Arize AX via OTLP."""
    from dotenv import load_dotenv

    load_dotenv()

    from src.config import BridgeSettings
    from src.export.otel_exporter import create_tracer_provider, shutdown_tracer_provider
    from src.export.span_builder import SpanBuilder

    settings = BridgeSettings()  # type: ignore[call-arg]

    # Optionally shift timestamps so every trace ends near "now".
    # Arize's span detail panel queries a narrow 2-day window around each
    # span's startTime.  If the data spans more than ~2 days, a single
    # global offset leaves older traces outside that window, causing blank
    # detail panels.  Shift each tree individually to avoid this.
    if shift_to_now and trees:
        now = datetime.now(timezone.utc)
        for root in trees:
            tree_end = root.end_time
            if tree_end.tzinfo is None:
                tree_end = tree_end.replace(tzinfo=timezone.utc)
            offset = now - tree_end
            shift_tree_timestamps(root, offset)
        logger.info("Shifted %d trees so each ends at now", len(trees))

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
        except Exception:
            logger.exception("Failed to export tree: %s", root.name)

    # Flush and shutdown
    logger.info("Flushing spans to Arize...")
    provider.force_flush()
    shutdown_tracer_provider(provider)
    logger.info(
        "Done. Exported %d/%d traces to Arize project '%s'",
        exported, len(trees), settings.arize_project_name,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Default: stats + diagnose when no action flags given
    if not any([args.stats, args.diagnose, args.export]):
        args.stats = True
        args.diagnose = True

    # Load events from all files
    all_events: list[AppInsightsEvent] = []
    for file_path in args.files:
        try:
            events = load_events_from_file(file_path)
            all_events.extend(events)
        except Exception as e:
            logger.error("Error loading %s: %s", file_path, e)
            sys.exit(1)

    logger.info("Total: %d events from %d file(s)", len(all_events), len(args.files))

    # Filter design-mode events unless --include-design-mode
    if not args.include_design_mode:
        before = len(all_events)
        all_events = [e for e in all_events if e.design_mode != "True"]
        filtered = before - len(all_events)
        if filtered:
            logger.info("Filtered %d design-mode events (%d remaining)", filtered, len(all_events))

    if not all_events:
        logger.info("No events to process.")
        return

    # Stats
    if args.stats:
        show_statistics(all_events)

    # Diagnose
    if args.diagnose:
        run_diagnostics(all_events)

    # Export
    if args.export:
        builder = TraceTreeBuilder()
        trees = builder.build_trees(all_events)
        logger.info("Built %d trace trees", len(trees))
        export_trees(trees, shift_to_now=args.shift_to_now)


if __name__ == "__main__":
    main()
