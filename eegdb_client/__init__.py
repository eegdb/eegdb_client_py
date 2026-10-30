"""EEGDB Python client: Fluent GUI, TCP CLI, readers, and analysis helpers."""

__version__ = "0.1.0"

__all__ = ["EEGDBEpochs", "EEGDBQueryClient", "EEGDBTrials", "SignalChunk"]


def __getattr__(name: str):
    """Load optional analysis helpers only when callers ask for them."""
    if name == "EEGDBEpochs":
        from .analysis import EEGDBEpochs

        return EEGDBEpochs
    if name == "EEGDBQueryClient":
        from .query_client import EEGDBQueryClient

        return EEGDBQueryClient
    if name in {"EEGDBTrials", "SignalChunk"}:
        from .analysis import EEGDBTrials, SignalChunk

        return {"EEGDBTrials": EEGDBTrials, "SignalChunk": SignalChunk}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
