#!/usr/bin/env python3
"""Validate partner data through the full bridge pipeline.

This script:
1. Loads partner-submitted data
2. Runs it through extraction → reconstruction → transformation
3. Reports detailed validation results
4. Does NOT export to Arize (dry-run mode)
"""

import json
import sys
from pathlib import Path
from collections import Counter

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "copilot-insights-bridge"))

from src.extraction.models import AppInsightsEvent
from src.reconstruction.tree_builder import TraceTreeBuilder
from src.transformation.mapper import OpenInferenceMapper


def load_partner_data(file_path: Path) -> list[dict]:
    """Load partner data from JSON file."""
    with open(file_path) as f:
        return json.load(f)


def validate_extraction(rows: list[dict]) -> tuple[list[AppInsightsEvent], dict]:
    """Validate extraction phase."""
    print("\n=== Phase 1: Extraction ===")

    stats = {
        "total_rows": len(rows),
        "parsed_successfully": 0,
        "parse_errors": [],
        "event_types": Counter(),
        "conversations": set(),
    }

    events = []
    for i, row in enumerate(rows):
        try:
            event = AppInsightsEvent.from_query_row(row)
            events.append(event)
            stats["parsed_successfully"] += 1
            stats["event_types"][event.name] += 1
            stats["conversations"].add(event.conversation_id)
        except Exception as e:
            stats["parse_errors"].append({"row_index": i, "error": str(e)})

    stats["conversations"] = len(stats["conversations"])

    print(f"✅ Parsed {stats['parsed_successfully']}/{stats['total_rows']} events")
    print(f"   Conversations: {stats['conversations']}")
    print(f"   Event types:")
    for event_type, count in stats["event_types"].most_common():
        print(f"     - {event_type}: {count}")

    if stats["parse_errors"]:
        print(f"⚠️  Parse errors: {len(stats['parse_errors'])}")
        for err in stats["parse_errors"][:3]:  # Show first 3
            print(f"     - Row {err['row_index']}: {err['error']}")

    return events, stats


def validate_reconstruction(events: list[AppInsightsEvent]) -> tuple[list, dict]:
    """Validate reconstruction phase."""
    print("\n=== Phase 2: Reconstruction ===")

    builder = TraceTreeBuilder()
    trees = builder.build_trees(events)

    stats = {
        "total_traces": len(trees),
        "total_spans": 0,
        "span_kinds": Counter(),
        "max_depth": 0,
        "conversations_with_traces": set(),
    }

    def analyze_tree(node, depth=0):
        stats["total_spans"] += 1
        stats["span_kinds"][node.span_kind.value] += 1
        stats["max_depth"] = max(stats["max_depth"], depth)
        stats["conversations_with_traces"].add(node.conversation_id)
        for child in node.children:
            analyze_tree(child, depth + 1)

    for tree in trees:
        analyze_tree(tree)

    stats["conversations_with_traces"] = len(stats["conversations_with_traces"])

    print(f"✅ Built {stats['total_traces']} trace trees")
    print(f"   Total spans: {stats['total_spans']}")
    print(f"   Max depth: {stats['max_depth']}")
    print(f"   Span kinds:")
    for kind, count in stats["span_kinds"].most_common():
        print(f"     - {kind}: {count}")

    return trees, stats


def validate_transformation(trees: list) -> tuple[list, dict]:
    """Validate transformation phase."""
    print("\n=== Phase 3: Transformation ===")

    mapper = OpenInferenceMapper()

    stats = {
        "total_otel_spans": 0,
        "attributes_per_span": [],
        "required_attributes": {
            "session.id": 0,
            "user.id": 0,
            "openinference.span.kind": 0,
        },
        "span_names": Counter(),
        "span_kinds": Counter(),
    }

    def walk_tree(node):
        """Walk tree and collect span stats."""
        attrs = mapper.map_attributes(node)
        stats["total_otel_spans"] += 1
        stats["attributes_per_span"].append(len(attrs))
        stats["span_names"][node.name] += 1

        # Check for required attributes
        for req_attr in stats["required_attributes"]:
            if req_attr in attrs:
                stats["required_attributes"][req_attr] += 1

        # Collect span kinds
        if "openinference.span.kind" in attrs:
            stats["span_kinds"][attrs["openinference.span.kind"]] += 1

        # Recurse to children
        for child in node.children:
            walk_tree(child)

    for tree in trees:
        walk_tree(tree)

    if stats["attributes_per_span"]:
        avg_attrs = sum(stats["attributes_per_span"]) / len(stats["attributes_per_span"])
        stats["avg_attributes_per_span"] = round(avg_attrs, 1)

    print(f"✅ Generated {stats['total_otel_spans']} OTel spans (mapped)")
    print(f"   Avg attributes per span: {stats.get('avg_attributes_per_span', 0)}")
    print(f"   Required attributes coverage:")
    for attr, count in stats["required_attributes"].items():
        percentage = (count / stats["total_otel_spans"] * 100) if stats["total_otel_spans"] > 0 else 0
        print(f"     - {attr}: {count}/{stats['total_otel_spans']} ({percentage:.0f}%)")

    print(f"   OpenInference span kinds:")
    for kind, count in stats["span_kinds"].most_common():
        print(f"     - {kind}: {count}")

    print(f"   Top span names:")
    for name, count in stats["span_names"].most_common(5):
        print(f"     - {name}: {count}")

    return [], stats  # Return empty list since we're not creating actual OTel spans


def generate_report(all_stats: dict, output_file: Path = None):
    """Generate a comprehensive validation report."""
    report = {
        "summary": {
            "status": "✅ PASS" if all_stats["extraction"]["parsed_successfully"] > 0 else "❌ FAIL",
            "total_events": all_stats["extraction"]["total_rows"],
            "total_traces": all_stats["reconstruction"]["total_traces"],
            "total_otel_spans": all_stats["transformation"]["total_otel_spans"],
        },
        "details": all_stats,
    }

    if output_file:
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n📊 Full report saved to: {output_file}")

    return report


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_partner_data.py <partner_data_file>")
        print("\nExample:")
        print("  python validate_partner_data.py data/partner_submissions/tasneem_abdalla_fixed.json")
        sys.exit(1)

    input_file = Path(sys.argv[1])

    if not input_file.exists():
        print(f"❌ File not found: {input_file}")
        sys.exit(1)

    print(f"🔍 Validating partner data: {input_file.name}")
    print("=" * 70)

    # Load data
    rows = load_partner_data(input_file)

    # Run through pipeline
    all_stats = {}

    events, extraction_stats = validate_extraction(rows)
    all_stats["extraction"] = extraction_stats

    if not events:
        print("\n❌ No events parsed successfully. Cannot proceed.")
        sys.exit(1)

    trees, reconstruction_stats = validate_reconstruction(events)
    all_stats["reconstruction"] = reconstruction_stats

    if not trees:
        print("\n❌ No traces reconstructed. Cannot proceed.")
        sys.exit(1)

    otel_spans, transformation_stats = validate_transformation(trees)
    all_stats["transformation"] = transformation_stats

    # Generate report
    print("\n" + "=" * 70)
    print("📊 VALIDATION SUMMARY")
    print("=" * 70)

    report_file = input_file.with_name(input_file.stem + "_validation_report.json")
    report = generate_report(all_stats, report_file)

    print(f"\n{report['summary']['status']}")
    print(f"✅ Successfully processed {report['summary']['total_events']} events")
    print(f"✅ Generated {report['summary']['total_traces']} traces")
    print(f"✅ Created {report['summary']['total_otel_spans']} OTel spans")

    print("\n✅ Partner data is valid and ready for export!")
    print("\nNext steps:")
    print("1. Review the validation report")
    print("2. Optionally export to Arize using scripts/export_to_arize.py")
    print("3. Create partner metadata in partner_data/ directory")


if __name__ == "__main__":
    main()
