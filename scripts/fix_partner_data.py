#!/usr/bin/env python3
"""Fix partner-submitted data to match bridge expectations.

This script:
1. Renames "timestamp [UTC]" to "timestamp"
2. Converts timestamp format if needed
3. Validates the data structure
"""

import json
import sys
from datetime import datetime
from pathlib import Path


def fix_timestamp_field(data: list[dict]) -> list[dict]:
    """Rename 'timestamp [UTC]' to 'timestamp' and ensure ISO format."""
    fixed = []
    for event in data:
        if "timestamp [UTC]" in event:
            # Rename the field
            event["timestamp"] = event.pop("timestamp [UTC]")

        # Ensure timestamp is in ISO format (try to parse and re-format)
        if "timestamp" in event and isinstance(event["timestamp"], str):
            ts = event["timestamp"]
            # Handle M/D/YYYY, H:MM:SS.mmm PM format (from Azure Portal export)
            if "/" in ts and "," in ts:
                try:
                    # Example: "2/27/2026, 2:47:13.411 PM"
                    dt = datetime.strptime(ts, "%m/%d/%Y, %I:%M:%S.%f %p")
                    event["timestamp"] = dt.isoformat() + "Z"
                except ValueError:
                    # Try without milliseconds
                    try:
                        dt = datetime.strptime(ts, "%m/%d/%Y, %I:%M:%S %p")
                        event["timestamp"] = dt.isoformat() + "Z"
                    except ValueError:
                        print(f"Warning: Could not parse timestamp: {ts}", file=sys.stderr)

        fixed.append(event)

    return fixed


def validate_structure(data: list[dict]) -> dict[str, any]:
    """Validate the data structure and return stats."""
    stats = {
        "total_events": len(data),
        "event_types": set(),
        "conversations": set(),
        "missing_fields": set(),
        "has_design_mode": False,
        "design_mode_values": set(),
    }

    required_fields = ["timestamp", "name"]

    for event in data:
        # Check required fields
        for field in required_fields:
            if field not in event:
                stats["missing_fields"].add(field)

        # Collect stats
        if "name" in event:
            stats["event_types"].add(event["name"])

        dims = event.get("customDimensions", {})
        if "conversationId" in dims:
            stats["conversations"].add(dims["conversationId"])

        if "DesignMode" in dims or "designMode" in dims:
            stats["has_design_mode"] = True
            dm = dims.get("DesignMode") or dims.get("designMode")
            stats["design_mode_values"].add(dm)

    # Convert sets to lists for JSON serialization
    stats["event_types"] = sorted(stats["event_types"])
    stats["conversations"] = len(stats["conversations"])
    stats["missing_fields"] = sorted(stats["missing_fields"])
    stats["design_mode_values"] = sorted(stats["design_mode_values"])

    return stats


def main():
    if len(sys.argv) < 2:
        print("Usage: python fix_partner_data.py <input_file> [output_file]")
        print("\nExample:")
        print("  python fix_partner_data.py sanitized_output.json fixed_output.json")
        sys.exit(1)

    input_file = Path(sys.argv[1])

    if len(sys.argv) >= 3:
        output_file = Path(sys.argv[2])
    else:
        # Default: add "_fixed" suffix
        output_file = input_file.with_name(input_file.stem + "_fixed" + input_file.suffix)

    print(f"Loading data from: {input_file}")
    with open(input_file) as f:
        data = json.load(f)

    print(f"Original events: {len(data)}")

    # Fix timestamp field
    print("Fixing timestamp field...")
    fixed_data = fix_timestamp_field(data)

    # Validate structure
    print("Validating structure...")
    stats = validate_structure(fixed_data)

    print("\n=== Validation Results ===")
    print(f"Total events: {stats['total_events']}")
    print(f"Event types: {', '.join(stats['event_types'])}")
    print(f"Conversations: {stats['conversations']}")
    print(f"DesignMode present: {stats['has_design_mode']}")
    print(f"DesignMode values: {', '.join(stats['design_mode_values'])}")

    if stats['missing_fields']:
        print(f"⚠️  Missing required fields: {', '.join(stats['missing_fields'])}")
    else:
        print("✅ All required fields present")

    # Save fixed data
    print(f"\nSaving fixed data to: {output_file}")
    with open(output_file, "w") as f:
        json.dump(fixed_data, f, indent=2)

    print("\n✅ Done!")
    print(f"Fixed data saved to: {output_file}")


if __name__ == "__main__":
    main()
