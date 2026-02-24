#!/usr/bin/env python3
"""Process partner-provided Copilot Studio telemetry data.

This script validates and processes partner data exports for testing the bridge
without requiring direct access to their Azure Application Insights resources.

Usage:
    python scripts/process_partner_data.py <input_file.json> [options]

Options:
    --diagnose      Run gap analysis diagnostics only (no export to Arize)
    --export        Export processed traces to Arize AX
    --output FILE   Save processed events to file (for inspection)
    --stats         Show statistics about the data
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, List, Dict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extraction.models import AppInsightsEvent
from src.reconstruction.tree_builder import TraceTreeBuilder
from src.transformation.mapper import OpenInferenceMapper


def load_partner_data(file_path: str) -> List[AppInsightsEvent]:
    """Load and parse partner data file.

    Handles both Azure CLI output format and direct event arrays.
    """
    with open(file_path, 'r') as f:
        data = json.load(f)

    # Handle Azure CLI format: {"tables": [{"rows": [...]}]}
    if isinstance(data, dict) and 'tables' in data:
        rows = data['tables'][0]['rows']
        events = []
        for row in rows:
            # Azure CLI returns array: [timestamp, name, operation_Id, operation_ParentId, customDimensions]
            if isinstance(row, list) and len(row) >= 5:
                event_data = {
                    'timestamp': row[0],
                    'name': row[1],
                    'operation_Id': row[2] or '',
                    'operation_ParentId': row[3] or '',
                    'customDimensions': row[4] if isinstance(row[4], dict) else json.loads(row[4])
                }
                events.append(AppInsightsEvent.from_query_row(event_data))
            # Or dict format
            elif isinstance(row, dict):
                events.append(AppInsightsEvent.from_query_row(row))

    # Handle direct array format
    elif isinstance(data, list):
        events = [AppInsightsEvent.from_query_row(event) for event in data]

    else:
        raise ValueError(f"Unexpected data format: {type(data)}")

    # Sort by timestamp
    events.sort(key=lambda e: e.timestamp)

    return events


def show_statistics(events: List[AppInsightsEvent]) -> None:
    """Display statistics about the partner data."""
    from collections import Counter

    print("\n" + "="*70)
    print("📊 PARTNER DATA STATISTICS")
    print("="*70)

    print(f"\nTotal events: {len(events)}")

    if not events:
        return

    # Time range
    start = min(e.timestamp for e in events)
    end = max(e.timestamp for e in events)
    print(f"Time range: {start} to {end}")
    print(f"Duration: {end - start}")

    # Event types
    print(f"\nEvent types:")
    event_counts = Counter(e.name for e in events)
    for name, count in event_counts.most_common():
        print(f"  {name}: {count}")

    # Conversations
    conv_ids = {e.conversation_id for e in events if e.conversation_id}
    print(f"\nUnique conversations: {len(conv_ids)}")

    # Sessions
    session_ids = {e.session_id for e in events if e.session_id}
    print(f"Unique sessions: {len(session_ids)}")

    # Channels
    channels = {e.channel_id for e in events if e.channel_id}
    print(f"Channels: {', '.join(channels) if channels else 'None'}")

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
        print(f"\nAgent types: {', '.join(agent_types)}")

    # Locales
    locales = {e.locale for e in events if e.locale}
    if locales:
        print(f"Locales: {', '.join(locales)}")

    print("="*70 + "\n")


def run_diagnostics(events: List[AppInsightsEvent]) -> None:
    """Run gap analysis diagnostics on partner data."""
    print("\n" + "="*70)
    print("🔍 RUNNING GAP ANALYSIS DIAGNOSTICS")
    print("="*70 + "\n")

    builder = TraceTreeBuilder()
    trees = builder.build_trees(events)

    print(f"Built {len(trees)} trace trees\n")

    # Count features detected
    knowledge_search_count = sum(1 for t in trees if t.knowledge_search_detected)
    system_topic_count = sum(
        1 for t in trees
        for child in t.children
        if hasattr(child, 'is_system_topic') and child.is_system_topic
    )

    print(f"Knowledge search detected: {knowledge_search_count} traces")
    print(f"System topics detected: {system_topic_count} spans")

    # Locale detection
    locales_in_trees = {t.locale for t in trees if t.locale}
    if locales_in_trees:
        print(f"Locales detected: {', '.join(locales_in_trees)}")

    # Empty traces
    empty_count = sum(
        1 for t in trees
        if not t.input_messages and not t.output_messages and not t.children
    )
    if empty_count:
        print(f"\n⚠️  Empty traces (would be filtered): {empty_count}")

    # Show sample tree structure
    if trees:
        print("\n📋 Sample trace structure:")
        sample = trees[0]
        print(f"  Root: {sample.name} ({sample.span_kind.value})")
        print(f"    Input: {len(sample.input_messages)} messages")
        print(f"    Output: {len(sample.output_messages)} messages")
        print(f"    Children: {len(sample.children)}")
        for child in sample.children[:3]:  # Show first 3 children
            print(f"      - {child.name} ({child.span_kind.value})")
            if child.children:
                print(f"        Grandchildren: {len(child.children)}")

    print("\n" + "="*70 + "\n")


def export_to_arize(events: List[AppInsightsEvent], config_path: str = ".env") -> None:
    """Export partner data to Arize AX (requires credentials).

    This reuses the export_to_arize.py logic.
    """
    print("\n" + "="*70)
    print("📤 EXPORTING TO ARIZE AX")
    print("="*70 + "\n")

    # Import the existing export script logic
    from src.config import BridgeSettings
    from src.export.otel_exporter import create_tracer_provider
    from src.export.span_builder import SpanBuilder

    # Load settings
    settings = BridgeSettings()  # type: ignore[call-arg]

    # Build trees
    builder = TraceTreeBuilder()
    trees = builder.build_trees(events)
    print(f"Built {len(trees)} trace trees")

    # Export
    provider = create_tracer_provider(
        space_id=settings.arize_space_id,
        api_key=settings.arize_api_key,
        project_name=settings.arize_project_name,
    )

    mapper = OpenInferenceMapper()
    span_builder = SpanBuilder(provider.get_tracer("partner-data-validation"))

    exported = 0
    for root in trees:
        try:
            span_builder.export_trace_tree(root, attributes_map=mapper.map_attributes)
            exported += 1
        except Exception as e:
            print(f"❌ Failed to export tree: {e}")

    provider.force_flush()
    print(f"\n✅ Successfully exported {exported}/{len(trees)} traces to Arize AX")
    print(f"   Project: {settings.arize_project_name}")
    print("\n" + "="*70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Process partner Copilot Studio telemetry data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Show statistics only
    python scripts/process_partner_data.py partner_data.json --stats

    # Run diagnostics
    python scripts/process_partner_data.py partner_data.json --diagnose

    # Export to Arize (requires .env configuration)
    python scripts/process_partner_data.py partner_data.json --export

    # All of the above
    python scripts/process_partner_data.py partner_data.json --stats --diagnose --export
        """
    )

    parser.add_argument('input_file', help='Partner data JSON file')
    parser.add_argument('--stats', action='store_true', help='Show data statistics')
    parser.add_argument('--diagnose', action='store_true', help='Run gap analysis diagnostics')
    parser.add_argument('--export', action='store_true', help='Export to Arize AX')
    parser.add_argument('--output', help='Save processed events to file')

    args = parser.parse_args()

    # Default: show stats if no actions specified
    if not any([args.stats, args.diagnose, args.export, args.output]):
        args.stats = True
        args.diagnose = True

    # Load data
    print(f"\n📂 Loading partner data from: {args.input_file}")
    try:
        events = load_partner_data(args.input_file)
        print(f"✅ Loaded {len(events)} events\n")
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        sys.exit(1)

    # Process based on options
    if args.stats:
        show_statistics(events)

    if args.diagnose:
        run_diagnostics(events)

    if args.output:
        output_data = [
            {
                'timestamp': e.timestamp.isoformat(),
                'name': e.name,
                'conversation_id': e.conversation_id,
                'session_id': e.session_id,
                'channel_id': e.channel_id,
                'topic_name': e.topic_name,
                'text': e.text,
                # Add more fields as needed
            }
            for e in events
        ]
        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"💾 Saved processed events to: {args.output}\n")

    if args.export:
        try:
            export_to_arize(events)
        except Exception as e:
            print(f"❌ Export failed: {e}")
            print("Ensure .env file is configured with Arize credentials")
            sys.exit(1)

    print("✨ Done!\n")


if __name__ == "__main__":
    main()
