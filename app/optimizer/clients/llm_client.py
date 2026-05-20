"""
Azure OpenAI client — single authoritative LLM integration.

Replaces / consolidates:
  ai_report_generator.py  lines 140-174  _get_client() module-level singleton
  ai_report_generator.py  lines 197-297  inline client.chat.completions.create() calls
  a2a_server.py           lines 96-175   _call_azure_openai_chat() urllib implementation

API-version drift bug fixed here:
  ai_report_generator.py used "2024-02-15-preview"
  a2a_server.py          used "2024-12-01-preview"
  This client uses "2024-12-01-preview" everywhere as the single default.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from optimizer.clients.base import BaseIntegrationClient, IntegrationError

logger = logging.getLogger(__name__)


@dataclass
class LLMClientConfig:
    api_key: str = ""
    endpoint: str = ""          # Azure OpenAI endpoint or APIM gateway URL
    deployment: str = "gpt-4"
    api_version: str = "2024-12-01-preview"   # single authoritative default
    timeout: float = 60.0
    apim_sub_key: str = ""      # Ocp-Apim-Subscription-Key when routing through APIM

    @classmethod
    def from_django_settings(cls) -> "LLMClientConfig":
        from django.conf import settings as s
        apim = getattr(s, "AZURE_APIM_ENDPOINT", "").strip()
        direct = getattr(s, "AZURE_OPENAI_ENDPOINT", "").strip()
        return cls(
            api_key=getattr(s, "AZURE_OPENAI_API_KEY", "").strip(),
            endpoint=apim or direct,
            deployment=getattr(s, "AZURE_OPENAI_DEPLOYMENT", "gpt-4").strip(),
            api_version=getattr(s, "AZURE_OPENAI_API_VERSION", "2024-12-01-preview").strip()
            or "2024-12-01-preview",
            timeout=float(getattr(s, "AZURE_OPENAI_TIMEOUT", 60)),
            apim_sub_key=getattr(s, "AZURE_APIM_SUB_KEY", "").strip(),
        )

    def is_configured(self) -> bool:
        return bool(self.endpoint and self.api_key)


class LLMClient(BaseIntegrationClient):
    """
    Azure OpenAI client backed by the openai SDK.

    Public methods:
      complete(system, user, ...)               -> Optional[str]
      complete_with_usage(system, user, ...)    -> (Optional[str], dict)
      calculate_cost_eur(prompt_tokens, ...)    -> float   (static)
    """

    def __init__(self, config: LLMClientConfig) -> None:
        super().__init__()
        self._config = config
        self._client = None  # lazy; built on first call

    def get_service_name(self) -> str:
        return "azure-openai"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_client(self):
        try:
            from openai import AzureOpenAI
        except ImportError:
            raise IntegrationError(
                service=self.get_service_name(),
                message="openai package is not installed (pip install openai)",
                retryable=False,
            )
        cfg = self._config
        if not cfg.is_configured():
            raise IntegrationError(
                service=self.get_service_name(),
                message="AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be set",
                retryable=False,
            )
        kwargs: Dict[str, Any] = {
            "api_key": cfg.api_key,
            "api_version": cfg.api_version,
            "azure_endpoint": cfg.endpoint,
        }
        if cfg.apim_sub_key:
            kwargs["default_headers"] = {"Ocp-Apim-Subscription-Key": cfg.apim_sub_key}
        return AzureOpenAI(**kwargs)

    def _get_client(self):
        if self._client is None:
            self._client = self._build_client()
        return self._client

    # ── Public API ─────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        if not self._config.is_configured():
            return False
        try:
            self._get_client().models.list()
            return True
        except Exception as exc:
            self._log.warning("LLM health check failed: %s", exc)
            return False

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> Optional[str]:
        """
        Single chat-completion. Returns content string or None if not configured.
        Raises IntegrationError on API failure (caller decides whether to retry).
        """
        if not self._config.is_configured():
            self._log.warning("Azure OpenAI not configured; skipping LLM call")
            return None
        try:
            response = self._get_client().chat.completions.create(
                model=self._config.deployment,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=self._config.timeout,
            )
            content = response.choices[0].message.content if response.choices else None
            return (content or "").strip() or None
        except Exception as exc:
            raise IntegrationError(
                service=self.get_service_name(),
                message=str(exc),
                retryable=True,
            ) from exc

    def complete_with_usage(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 2500,
        temperature: float = 0.2,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Like complete(), but also returns token-usage metadata for cost tracking.
        Returns (content, {"prompt_tokens": int, "completion_tokens": int, ...})
        """
        if not self._config.is_configured():
            return None, {}
        try:
            response = self._get_client().chat.completions.create(
                model=self._config.deployment,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=self._config.timeout,
            )
            content = response.choices[0].message.content if response.choices else None
            usage = response.usage
            meta: Dict[str, Any] = {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0),
                "model": self._config.deployment,
            }
            return (content or "").strip() or None, meta
        except Exception as exc:
            raise IntegrationError(
                service=self.get_service_name(),
                message=str(exc),
                retryable=True,
            ) from exc

    @staticmethod
    def calculate_cost_eur(prompt_tokens: int, completion_tokens: int) -> float:
        """
        Estimate LLM cost in EUR (GPT-4 Azure pricing).
        Rates: $0.03/1K prompt, $0.06/1K completion, 0.93 USD→EUR conversion.
        """
        USD_TO_EUR = 0.93
        cost_usd = (prompt_tokens / 1_000) * 0.03 + (completion_tokens / 1_000) * 0.06
        return round(cost_usd * USD_TO_EUR, 6)
