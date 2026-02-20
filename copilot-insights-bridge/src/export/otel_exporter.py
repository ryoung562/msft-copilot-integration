"""TracerProvider and OTLP exporter setup for Arize AX."""

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_ARIZE_OTLP_ENDPOINT = "otlp.arize.com:443"


def create_tracer_provider(
    space_id: str,
    api_key: str,
    project_name: str,
) -> TracerProvider:
    """Create a TracerProvider configured to export spans to Arize AX via OTLP/gRPC.

    Args:
        space_id: Arize workspace identifier sent as OTLP metadata.
        api_key: Arize API key sent as OTLP metadata.
        project_name: Logical project name; used as ``model_id`` resource attribute.

    Returns:
        A fully-configured ``TracerProvider`` ready for span creation.
    """
    resource = Resource.create(
        {
            "model_id": project_name,
            "model_version": "1.0",
        }
    )

    exporter = OTLPSpanExporter(
        endpoint=_ARIZE_OTLP_ENDPOINT,
        headers={
            "space_id": space_id,
            "api_key": api_key,
        },
        insecure=False,
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def shutdown_tracer_provider(provider: TracerProvider) -> None:
    """Flush pending spans and shut down the provider."""
    provider.force_flush()
    provider.shutdown()
