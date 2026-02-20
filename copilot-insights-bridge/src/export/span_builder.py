"""Build OpenTelemetry SDK spans from a reconstructed SpanNode tree."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime
from typing import Any

from opentelemetry import trace as trace_api
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    StatusCode,
    TraceFlags,
    Tracer,
)

from src.reconstruction.span_models import SpanNode


def _dt_to_ns(dt: datetime) -> int:
    """Convert a datetime to nanoseconds since epoch (OTel SDK format)."""
    return int(dt.timestamp() * 1e9)


class SpanBuilder:
    """Creates OTel SDK spans from an internal ``SpanNode`` tree.

    This is designed for *historical* span export: start/end times and
    parent-child relationships are set explicitly rather than captured from
    live instrumentation.
    """

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    def export_trace_tree(
        self,
        root: SpanNode,
        attributes_map: Callable[[SpanNode], dict[str, Any]],
    ) -> None:
        """Walk *root* depth-first and emit an OTel span for every node.

        Args:
            root: Root of the span tree to export.
            attributes_map: Callable that converts a ``SpanNode`` into a flat
                dict of span attributes.
        """
        # Create root span without a parent context so it becomes a true root.
        # The SDK assigns a random trace_id; children inherit it via parent linkage.
        self._build_span(root, trace_id=None, parent_span_id=0, attributes_map=attributes_map)

    def _build_span(
        self,
        node: SpanNode,
        trace_id: int | None,
        parent_span_id: int,
        attributes_map: Callable[[SpanNode], dict[str, Any]],
    ) -> None:
        if parent_span_id and trace_id:
            # Child span: link to parent via context so it shares the trace_id.
            parent_ctx = self._make_parent_context(trace_id, parent_span_id)
        else:
            # Root span: no parent context → SDK creates a true root span.
            parent_ctx = None

        mapped_attrs = attributes_map(node)

        span = self._tracer.start_span(
            name=node.name,
            context=parent_ctx,
            attributes=mapped_attrs,
            start_time=_dt_to_ns(node.start_time),
        )

        # Record errors as exception events and set status.
        for error in node.errors:
            span.add_event("exception", {"exception.message": error})
        if node.errors:
            span.set_status(StatusCode.ERROR, node.errors[0])

        span.end(end_time=_dt_to_ns(node.end_time))

        # Read the actual IDs assigned by the SDK for parent linkage.
        span_ctx = span.get_span_context()
        actual_span_id = span_ctx.span_id
        actual_trace_id = span_ctx.trace_id

        # Recurse into children with the current span as parent.
        for child in node.children:
            self._build_span(
                child, actual_trace_id, parent_span_id=actual_span_id, attributes_map=attributes_map
            )

    @staticmethod
    def _make_parent_context(trace_id: int, span_id: int) -> trace_api.Context:
        """Return an OTel ``Context`` carrying a ``NonRecordingSpan`` that
        represents a historical parent with the given IDs."""
        parent_span_context = SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            is_remote=False,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )
        parent_span = NonRecordingSpan(parent_span_context)
        return trace_api.set_span_in_context(parent_span)
