from __future__ import annotations

from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import OpenAI, BadRequestError

from ..config import AppConfig


class LLMClient:
    def __init__(self, config: AppConfig):
        headers = None
        self.client = OpenAI(
            api_key=config.openai_api_key or None,
            base_url=config.openai_base_url or None,
            default_headers=headers,
        )
        self.model = config.openai_model

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
    )
    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 1.0,
        json_response: bool = False,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # Some models only accept default temperature. Omit it unless explicitly non-default.
        kwargs = {
            "model": self.model,
            "messages": messages,
        }
        if temperature is not None and temperature != 1:
            kwargs["temperature"] = temperature

        if json_response:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = self.client.chat.completions.create(timeout=getattr(self.client, "timeout", None) or  None, **kwargs)
        except BadRequestError as e:
            # Retry logic for temperature
            if "temperature" in str(e):
                kwargs.pop("temperature", None)
            # Retry logic for response_format not supported
            if "response_format" in kwargs and "response_format" in str(e):
                kwargs.pop("response_format", None)
            # Final retry attempt without offending params
            resp = self.client.chat.completions.create(timeout=getattr(self.client, "timeout", None) or None, **kwargs)
        return resp.choices[0].message.content or ""


