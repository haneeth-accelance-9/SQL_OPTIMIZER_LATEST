"""
This agent creates executive summary or the results that are obtained by applying usecases on the data

This module provides an A2A (Agent-to-Agent) protocol server,
enabling integration with other AI agents and systems.
"""

import os
import json
from typing import Any, Optional

# Import AgenticAI SDK
from agenticai.a2a import A2AFactory

# Import local tools
try:
    from . import tools  # noqa: F401
except ImportError:
    import tools  # noqa: F401


def _register_deterministic_routes(fastapi_app: Any) -> None:
    """
    Register deterministic (non-LLM) HTTP endpoints on the agent server.

    Why this exists:
    - The phased A2A workflow uses the LLM as an orchestrator, which can fail with 429 throttling.
    - The Django app can call these endpoints directly to always get a report, without any LLM call.
    """
    try:
        from fastapi import APIRouter  # type: ignore
        from pydantic import BaseModel, Field  # type: ignore
    except Exception:
        # If FastAPI/pydantic aren't available for some reason, skip route registration.
        return

    import time
    import logging
    from pathlib import Path
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    logger = logging.getLogger(__name__)

    # Local imports (agent tools)
    try:
        from .tools.evaluate_optimization_rules import evaluate_optimization_rules
        from .tools.report_generator import report_generator
    except Exception:
        from tools.evaluate_optimization_rules import evaluate_optimization_rules  # type: ignore
        from tools.report_generator import report_generator  # type: ignore

    class GenerateReportRequest(BaseModel):
        usecase_id: str = Field(..., description="Use case identifier for the report title")
        records: list[dict[str, Any]] = Field(..., description="Normalized records (snake_case keys)")
        strategy_results: dict[str, Any] = Field(
            default_factory=dict, description="Upstream strategy outputs (JSON object)"
        )
        notes: Optional[str] = Field(default=None, description="Optional context notes")
        llm_first: bool = Field(
            default=True,
            description="If true, attempt LLM-written report first; fall back to deterministic report on failure.",
        )
        llm_max_retries: int = Field(default=2, description="Max retries on LLM 429/5xx before fallback.")
        llm_timeout_seconds: int = Field(default=60, description="Timeout for the LLM request.")

    router = APIRouter()

    def _load_rules_yaml_text() -> str:
        # rules.base.yaml is shipped as package-data; resolve relative to this file in repo layout
        try:
            rules_path = Path(__file__).resolve().parents[2] / "configs" / "rules.base.yaml"
            return rules_path.read_text(encoding="utf-8")
        except Exception:
            return ""

    def _call_azure_openai_chat(
        *, system: str, user: str, timeout_seconds: int
    ) -> tuple[str, dict[str, Any]]:
        """
        Minimal Azure OpenAI Chat Completions call using stdlib only.
        Uses environment variables already used by your agent config:
        - AZURE_OPENAI_ENDPOINT
        - AZURE_OPENAI_DEPLOYMENT_NAME
        - AZURE_OPENAI_API_VERSION
        - AZURE_OPENAI_API_KEY  (may be APIM subscription key)
        """
        endpoint = (os.environ.get("AZURE_OPENAI_ENDPOINT") or "").rstrip("/")
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME") or os.environ.get("AZURE_OPENAI_DEPLOYMENT") or ""
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION") or "2024-12-01-preview"
        key = os.environ.get("AZURE_OPENAI_API_KEY") or ""

        if not endpoint or not deployment or not key:
            raise RuntimeError("Missing Azure OpenAI env vars (endpoint/deployment/api_key).")

        url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": 2500,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            # Support both direct Azure OpenAI ("api-key") and APIM gateway ("Ocp-Apim-Subscription-Key")
            "api-key": key,
            "Ocp-Apim-Subscription-Key": key,
        }
        req = Request(url, data=body, headers=headers, method="POST")
        started = time.time()
        # High-signal, low-risk confirmation log (no secrets).
        logger.info(
            "Calling Azure OpenAI chat completions (deployment=%s api_version=%s endpoint_host=%s)",
            deployment,
            api_version,
            (endpoint.split("://", 1)[-1] if "://" in endpoint else endpoint),
        )
        with urlopen(req, timeout=timeout_seconds) as resp:
            status = getattr(resp, "status", None)
            resp_headers = dict(getattr(resp, "headers", {}) or {})
            raw = resp.read().decode("utf-8")
        elapsed_ms = int((time.time() - started) * 1000)
        data = json.loads(raw)
        choice0 = (data.get("choices") or [{}])[0]
        msg = choice0.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("LLM returned empty content.")
        meta = {
            "http_status": status,
            "elapsed_ms": elapsed_ms,
            # Common Azure/AOAI request id headers (may vary by gateway)
            "request_id": resp_headers.get("x-request-id")
            or resp_headers.get("x-ms-request-id")
            or resp_headers.get("apim-request-id"),
            "model": deployment,
        }
        logger.info(
            "Azure OpenAI chat completions succeeded (status=%s elapsed_ms=%s request_id=%s deployment=%s)",
            status,
            elapsed_ms,
            meta["request_id"],
            deployment,
        )
        return content.strip() + "\n", meta

    def _llm_write_report(
        *,
        usecase_id: str,
        rules_yaml: str,
        rules_evaluation: dict[str, Any],
        strategy_results: dict[str, Any],
        deterministic_markdown: str,
        timeout_seconds: int,
    ) -> tuple[str, dict[str, Any]]:
        system = (
            "You are an IT optimization reporting assistant. "
            "Write a professional, executive-facing Markdown report. "
            "Do not include raw JSON. Do not mention tools, phases, or internal process."
        )
        user = (
            f"Use case id: {usecase_id}\n\n"
            "## Use cases (rules.base.yaml)\n"
            f"{rules_yaml}\n\n"
            "## Rule evaluation results (JSON)\n"
            f"{json.dumps(rules_evaluation, ensure_ascii=False, indent=2)}\n\n"
            "## Strategy results (JSON)\n"
            f"{json.dumps(strategy_results, ensure_ascii=False, indent=2)}\n\n"
            "## Deterministic draft (for structure; you may improve wording)\n"
            f"{deterministic_markdown}\n\n"
            "### Output requirements\n"
            "- Output ONLY Markdown.\n"
            "- Include: Executive summary, Key findings table (rule id + matched count), "
            "per-rule sections with purpose + logic + results + evidence hosts, recommended actions, risks/caveats.\n"
            "- Use numbers from the provided JSON; do not invent counts.\n"
        )
        return _call_azure_openai_chat(system=system, user=user, timeout_seconds=timeout_seconds)

    @router.post("/generate-report")
    def generate_report(req: GenerateReportRequest) -> dict[str, Any]:
        """
        LLM-first report generator (with deterministic fallback):
        - runs evaluate_optimization_rules
        - generates deterministic markdown via report_generator
        - if llm_first=true: attempts to have the LLM write the final report, else uses deterministic markdown
        - always returns a report_markdown (unless evaluation itself fails)
        """
        eval_json_str = evaluate_optimization_rules(records_json=json.dumps(req.records))
        eval_obj = json.loads(eval_json_str) if eval_json_str else {"success": False, "error": "Empty evaluation"}

        if not eval_obj or not eval_obj.get("success", False):
            return {"success": False, "error": eval_obj.get("error") or "Rules evaluation failed", "rules_evaluation": eval_obj}

        report_json_str = report_generator(
            usecase_id=req.usecase_id,
            strategy_results_json=json.dumps(req.strategy_results or {}),
            rules_evaluation_json=json.dumps(eval_obj),
            notes=req.notes,
        )
        report_obj = json.loads(report_json_str) if report_json_str else {"success": False, "error": "Empty report"}

        if not report_obj.get("success"):
            return {
                "success": False,
                "error": report_obj.get("error") or "Report generation failed",
                "rules_evaluation": eval_obj,
            }

        deterministic_md = report_obj.get("markdown", "") or ""
        final_md = deterministic_md
        llm_used = False
        llm_error: Optional[str] = None
        llm_meta: dict[str, Any] = {}

        if req.llm_first:
            rules_yaml = _load_rules_yaml_text()
            # Retry on 429/5xx with small exponential backoff; then fall back.
            for attempt in range(max(0, int(req.llm_max_retries)) + 1):
                try:
                    final_md, llm_meta = _llm_write_report(
                        usecase_id=req.usecase_id,
                        rules_yaml=rules_yaml,
                        rules_evaluation=eval_obj,
                        strategy_results=req.strategy_results or {},
                        deterministic_markdown=deterministic_md,
                        timeout_seconds=int(req.llm_timeout_seconds),
                    )
                    llm_used = True
                    llm_error = None
                    break
                except HTTPError as e:
                    llm_error = f"HTTPError {e.code}"
                    if e.code in (429, 500, 502, 503, 504) and attempt < int(req.llm_max_retries):
                        time.sleep(2 ** attempt)
                        continue
                    break
                except (URLError, TimeoutError) as e:
                    llm_error = f"URLError/Timeout: {e}"
                    if attempt < int(req.llm_max_retries):
                        time.sleep(2 ** attempt)
                        continue
                    break
                except Exception as e:
                    llm_error = str(e)
                    break

        return {
            "success": True,
            "usecase_id": req.usecase_id,
            "rules_evaluation": eval_obj,
            "report_markdown": final_md,
            "llm_used": llm_used,
            "llm_error": llm_error,
            "llm_meta": llm_meta if llm_used else None,
            "deterministic_report_markdown": deterministic_md,
        }

    fastapi_app.include_router(router)


def main():
    """
    Start the A2A server.

    All configuration is loaded from the config file specified by the CONFIG_PATH
    environment variable, or defaults to config.yaml if not set.
    
    Supports debugpy for VS Code debugging when DEBUGPY_ENABLE=true environment variable is set.
    """
    # Check if debugger should be enabled
    if os.environ.get("DEBUGPY_ENABLE", "").lower() == "true":
        try:
            import debugpy
            
            debugpy.listen(("0.0.0.0", 5678))  # nosec B104 - Intentional for debugger access
            print("Debugger enabled - listening on port 5678")
            
            # Only wait for client if DEBUGPY_WAIT is set (Docker mode)
            if os.environ.get("DEBUGPY_WAIT", "").lower() == "true":
                print("   Waiting for VS Code debugger to attach...")
                debugpy.wait_for_client()
                print("Debugger attached!")
            else:
                print("   Server starting - attach debugger when ready")
        except ImportError:
            print("WARNING: debugpy not installed - continuing without debugger")
        except Exception as e:
            print(f"WARNING: Failed to start debugger: {e}")
    
    factory = A2AFactory()
    server = factory.create_server()
    # Add deterministic routes (no LLM / no A2A orchestration required)
    _register_deterministic_routes(server.fastapi_app)
    server.run()


if __name__ == "__main__":
    main()