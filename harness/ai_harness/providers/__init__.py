"""Bounded provider adapters."""

from .base import Provider, ProviderResult
from .cli_provider import CliProvider

__all__ = ["CliProvider", "Provider", "ProviderResult"]
