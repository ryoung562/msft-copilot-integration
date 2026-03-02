#!/usr/bin/env python3
"""Offline diagnostic: run the pipeline against a data dump and report on new
gap-analysis flags (knowledge search, system topics, unknown events, empty
trace filtering, locale).

Usage:
    python scripts/diagnose_gaps.py                    # uses real_data_dump.json
    python scripts/diagnose_gaps.py live_data_dump.json # uses a specific fixture
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extraction.loader import load_events_from_file
from src.reconstruction.tree_builder import TraceTreeBuilder
from src.reconstruction.span_models import SpanKind
from src.transformation.mapper import OpenInferenceMapper

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def main() -> None:
    # --- Load & parse ---
    arg = sys.argv[1] if len(sys.argv) > 1 else "real_data_dump.json"
    # If a bare filename is given, look in the fixtures directory
    path = Path(arg)
    if not path.exists() and not path.is_absolute():
        path = FIXTURES_DIR / arg
    events = load_events_from_file(path)
    print(f"Loaded {len(events)} raw events from {path.name}\n")

    # --- Show raw event type breakdown ---
    event_counts: dict[str, int] = {}
    for e in events:
        event_counts[e.name] = event_counts.get(e.name, 0) + 1
    print("--- Raw Event Types ---")
    for name, count in sorted(event_counts.items(), key=lambda x: -x[1]):
        print(f"  {name:<30} {count}")
    print()

    # --- Build trees ---
    builder = TraceTreeBuilder()

    # Build WITHOUT filtering to see what would be filtered
    all_events_trees = builder.build_trees(events)
    print(f"--- Trace Summary ---")
    print(f"  Total traces produced:        {len(all_events_trees)}")

    # --- Analyze each trace ---
    mapper = OpenInferenceMapper()

    knowledge_traces = []
    system_topic_chains = []
    custom_topic_chains = []
    unknown_event_spans = []
    empty_filtered = 0
    locales_seen: set[str] = set()

    for root in all_events_trees:
        # Check knowledge search
        if root.knowledge_search_detected:
            input_text = root.input_messages[0][:60] if root.input_messages else "(no input)"
            output_text = root.output_messages[0][:80] if root.output_messages else "(no output)"
            knowledge_traces.append((input_text, output_text, len(root.children)))

        # Check locale
        if root.locale:
            locales_seen.add(root.locale)

        # Check empty
        if not root.input_messages and not root.output_messages and not root.children:
            empty_filtered += 1

        # Walk children
        for chain in root.children:
            if chain.span_kind != SpanKind.CHAIN:
                continue

            if chain.is_system_topic:
                system_topic_chains.append(chain.name)
            else:
                custom_topic_chains.append(chain.name)

            for child in chain.children:
                # Check for unknown-event TOOL spans (not from Action/TopicAction)
                if child.span_kind == SpanKind.TOOL:
                    is_from_known_action = any(
                        e.name in ("Action", "TopicAction")
                        for e in child.raw_events
                    )
                    if not is_from_known_action:
                        unknown_event_spans.append(
                            (child.name, child.raw_events[0].name if child.raw_events else "?")
                        )

    # --- Report ---
    print(f"  Empty traces (filtered out):  {empty_filtered}")
    print(f"  Locales seen:                 {locales_seen or '(none)'}")
    print()

    print(f"--- Knowledge Search Detection ({len(knowledge_traces)} traces) ---")
    if knowledge_traces:
        for inp, out, n_children in knowledge_traces:
            children_note = f"{n_children} children" if n_children else "no children (orchestrator-only)"
            print(f"  Input:    {inp}")
            print(f"  Output:   {out}")
            print(f"  Children: {children_note}")
            print()
    else:
        print("  (none detected)")
    print()

    print(f"--- System Topic Chains ({len(system_topic_chains)}) ---")
    if system_topic_chains:
        from collections import Counter
        for name, count in Counter(system_topic_chains).most_common():
            print(f"  {name:<50} x{count}")
    else:
        print("  (none detected)")
    print()

    print(f"--- Custom Topic Chains ({len(custom_topic_chains)}) ---")
    if custom_topic_chains:
        from collections import Counter
        for name, count in Counter(custom_topic_chains).most_common():
            print(f"  {name:<50} x{count}")
    else:
        print("  (none detected)")
    print()

    print(f"--- Unknown Event TOOL Spans ({len(unknown_event_spans)}) ---")
    if unknown_event_spans:
        for tool_name, event_name in unknown_event_spans:
            print(f"  Tool: {tool_name:<30} from event: {event_name}")
    else:
        print("  (none — all events matched known types)")
    print()

    # --- Sample mapper output for one trace with new fields ---
    print("--- Sample Mapper Output (first trace with new flags) ---")
    for root in all_events_trees:
        attrs = mapper.map_attributes(root)
        meta = json.loads(attrs.get("metadata", "{}"))
        has_new = any(
            k in meta
            for k in ("knowledge_search_detected", "is_system_topic", "topic_type", "locale")
        )
        if has_new:
            print(f"  Span:     {root.name}")
            print(f"  Tags:     {attrs.get('tag.tags')}")
            print(f"  Metadata: {json.dumps(meta, indent=4)}")
            break
    else:
        # Fall back to first trace
        if all_events_trees:
            root = all_events_trees[0]
            attrs = mapper.map_attributes(root)
            meta = json.loads(attrs.get("metadata", "{}"))
            print(f"  Span:     {root.name}")
            print(f"  Tags:     {attrs.get('tag.tags')}")
            print(f"  Metadata: {json.dumps(meta, indent=4)}")
        else:
            print("  (no traces)")


if __name__ == "__main__":
    main()
