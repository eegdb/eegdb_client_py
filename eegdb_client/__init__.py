"""EEGDB Python client: Fluent GUI, TCP CLI, readers, and analysis helpers."""

__version__ = "0.1.0"

__all__ = ["EEGDBEpochs"]


def __getattr__(name: str):
    """Load optional analysis helpers only when callers ask for them."""
    if name == "EEGDBEpochs":
        from .analysis import EEGDBEpochs

        return EEGDBEpochs
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
