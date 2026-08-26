"""Data-access layer of the API.

Read repositories shared with the ingestor (e.g. corpus/quiz retrieval) live in
`commons/repositories/db/`; this package holds repositories specific to the API only.
"""

from .agent_config_repository import AgentConfigRepository

__all__ = ["AgentConfigRepository"]
