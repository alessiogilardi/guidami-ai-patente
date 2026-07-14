"""Base agents shared between ingestor and application."""

from .base_agent import BaseAgent
from .configs import AgentConfig

__all__ = ["AgentConfig", "BaseAgent"]
