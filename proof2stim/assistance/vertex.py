"""Explicitly capped Vertex AI Gemini proposal invocation."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from proof2stim.assistance.proposal import (
    PROJECT_ROOT,
    ProposalValidationError,
    parse_proposal,
    project_file,
    validate_proposal,
    validate_request,
)


def estimated_cost_usd(
    input_tokens: int,
    output_tokens: int,
    input_usd_per_million: float,
    output_usd_per_million: float,
) -> float:
    """Calculate a token-price estimate using caller-supplied published rates."""

    if min(input_tokens, output_tokens) < 0:
        raise ProposalValidationError("token counts cannot be negative")
    if min(input_usd_per_million, output_usd_per_million) < 0:
        raise ProposalValidationError("token prices cannot be negative")
    return round(
        (input_tokens * input_usd_per_million + output_tokens * output_usd_per_million) / 1_000_000,
        9,
    )


def maximum_request_cost_usd(
    request: dict[str, Any],
    input_usd_per_million: float,
    output_usd_per_million: float,
) -> float:
    """Estimate the configured worst case before making a provider request."""

    return estimated_cost_usd(
        request["conservative_input_token_bound"],
        request["generation_config"]["max_output_tokens"],
        input_usd_per_million,
        output_usd_per_million,
    )


def _usage_value(usage: object, field: str) -> int:
    if usage is None:
        return 0
    value = usage.get(field, 0) if isinstance(usage, dict) else getattr(usage, field, 0)
    return int(value or 0)


def _new_client(project: str, location: str, provider_controls: dict[str, Any]) -> object:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise ProposalValidationError(
            "Google Gen AI SDK is not installed; install the project with the 'gemini' extra"
        ) from exc
    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
        http_options=types.HttpOptions(
            api_version=provider_controls["api_version"],
            timeout=provider_controls["timeout_seconds"] * 1000,
            retry_options=types.HttpRetryOptions(attempts=provider_controls["max_attempts"]),
        ),
    )


def invoke_vertex_proposal(
    request: dict[str, Any],
    *,
    project: str,
    location: str,
    model: str,
    input_usd_per_million: float,
    output_usd_per_million: float,
    cost_cap_usd: float,
    project_root: Path = PROJECT_ROOT,
    client: object | None = None,
) -> dict[str, Any]:
    """Call Gemini once, then validate its JSON as an untrusted proposal."""

    if not all(value.strip() for value in (project, location, model)):
        raise ProposalValidationError("project, location, and model are required")
    if cost_cap_usd <= 0:
        raise ProposalValidationError("cost cap must be greater than zero")
    validate_request(request, project_root=project_root)
    maximum_cost = maximum_request_cost_usd(request, input_usd_per_million, output_usd_per_million)
    if maximum_cost > cost_cap_usd:
        raise ProposalValidationError(
            f"configured worst-case cost ${maximum_cost:.6f} exceeds cap ${cost_cap_usd:.6f}"
        )

    root = project_root.resolve()
    response_schema = json.loads(
        project_file(root, request["response_schema"]).read_text(encoding="utf-8")
    )
    generation_config = dict(request["generation_config"])
    generation_config["response_json_schema"] = response_schema
    active_client = (
        client
        if client is not None
        else _new_client(project, location, request["provider_controls"])
    )

    started_at = datetime.now(UTC)
    started_clock = time.perf_counter()
    try:
        response = active_client.models.generate_content(
            model=model,
            contents=request["prompt"],
            config=generation_config,
        )
    except Exception as exc:
        raise ProposalValidationError(f"Vertex Gemini request failed: {exc}") from exc
    latency = round(time.perf_counter() - started_clock, 6)
    response_text = getattr(response, "text", None)
    if not response_text:
        raise ProposalValidationError("Vertex Gemini response contained no text")
    proposal = parse_proposal(response_text)
    checks = validate_proposal(proposal, request, project_root=root)

    usage_metadata = getattr(response, "usage_metadata", None)
    usage = {
        "input_tokens": _usage_value(usage_metadata, "prompt_token_count"),
        "output_tokens": _usage_value(usage_metadata, "candidates_token_count"),
        "thinking_tokens": _usage_value(usage_metadata, "thoughts_token_count"),
        "cached_input_tokens": _usage_value(usage_metadata, "cached_content_token_count"),
        "total_tokens": _usage_value(usage_metadata, "total_token_count"),
    }
    return {
        "proposal": proposal,
        "started_utc": started_at.isoformat(),
        "finished_utc": datetime.now(UTC).isoformat(),
        "latency_seconds": latency,
        "usage": usage,
        "estimated_cost_usd": estimated_cost_usd(
            usage["input_tokens"],
            usage["output_tokens"] + usage["thinking_tokens"],
            input_usd_per_million,
            output_usd_per_million,
        ),
        "validation_checks": checks,
        "maximum_request_cost_usd": maximum_cost,
    }
