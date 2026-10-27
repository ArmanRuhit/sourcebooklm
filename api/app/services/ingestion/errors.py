"""Failures that are safe to surface in `sources.error`."""


class IngestionError(Exception):
    """A source-specific failure; the worker records the message and moves on."""
