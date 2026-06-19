"""Agenti base condivisi tra ingestor e applicativo."""

from ..configs.agent_config import AgentConfig
from .base_agent import BaseAgent

__all__ = ["AgentConfig", "BaseAgent"]
