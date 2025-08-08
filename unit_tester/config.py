from __future__ import annotations

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    """Application configuration loaded from environment variables."""

    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_base_url: str | None = Field(default=None, description="Optional custom base URL")
    openai_model: str = Field(default="gpt-5-nano", description="Default OpenAI model")
    request_timeout_s: float = Field(default=60.0, description="Per-request timeout in seconds")
    planner_concurrency: int = Field(default=3, description="Max concurrent LLM calls during planning")

    # Discovery
    ignore_globs: List[str] = Field(
        default_factory=lambda: [
            "**/.git/**",
            "**/.venv/**",
            "**/node_modules/**",
            "**/dist/**",
            "**/build/**",
            "**/.unit_tester/**",
        ]
    )

    class Config:
        env_file = ".env"
        env_prefix = ""
        extra = "ignore"


