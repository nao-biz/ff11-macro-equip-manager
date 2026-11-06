"""Repository specification maintenance, independent of CLI/MCP transports."""

from .service import SpecError, SpecService

__all__ = ["SpecError", "SpecService"]
