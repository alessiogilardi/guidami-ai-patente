"""Lazy DI builder for the `evaluate-retrieval-judge` script's retrieval-judge agent."""

from pathlib import Path

from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from commons.ai.observability import LlmCallTracker
from commons.clients.file_system import LocalFileSystemClient
from commons.repositories import YamlRepository

from .agents import RetrievalJudgeAgent


def build_retrieval_judge_agent(
    agents_dir: Path, provider: OpenRouterProvider, tracker: LlmCallTracker
) -> RetrievalJudgeAgent:
    """Loads `retrieval_judge.yaml` from `agents_dir` (evaluation-only agent)."""
    agents_repository = YamlRepository(
        AgentConfig, file_system_client=LocalFileSystemClient(agents_dir)
    )
    return RetrievalJudgeAgent.from_yaml(
        "retrieval_judge", agents_repository, provider, tracker=tracker
    )
