"""Rule-based and API-backed providers for dispatch briefings."""

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Optional, Protocol

from briefing.schema import BriefingNarrative
from evals.checks import expected_route_risks

PROVIDER_TIMEOUT_SECONDS = 20.0
GUNICORN_TIMEOUT_SECONDS = 45
GROQ_REQUEST_TIMEOUT_SECONDS = 30.0
MAX_RATE_LIMIT_WAIT_SECONDS = 10.0
_logger = logging.getLogger(__name__)


@dataclass
class ProviderResponse:
    text: str
    tokens: int
    latency_ms: float
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    finish_reason: Optional[str] = None
    wait_ms: float = 0.0
    wait_events: Optional[list] = None


class ProviderRequestError(RuntimeError):
    """Raised when a hosted provider request fails."""


class ProviderConfigurationError(RuntimeError):
    """Raised when a production deployment has not selected a provider."""


class Provider(Protocol):
    def generate(self, system: str, user: str) -> ProviderResponse:
        ...


class MockProvider:
    def __init__(self, mode: Optional[str] = None):
        self.mode = (mode or os.getenv("MOCK_MODE", "normal")).lower()
        if self.mode not in {
            "normal",
            "faulty",
            "faulty_number",
            "faulty_place",
            "faulty_route_id",
            "faulty_safe",
        }:
            raise ValueError(
                "MOCK_MODE must be 'normal', 'faulty', 'faulty_number', "
                "'faulty_place', 'faulty_route_id', or 'faulty_safe'."
            )

    def generate(self, system: str, user: str) -> ProviderResponse:
        started = time.perf_counter()
        try:
            match = re.search(
                r"(?s)^.*?BEGIN_UNTRUSTED_ROUTE_PLAN_DATA\n(.*?)\n"
                r"END_UNTRUSTED_ROUTE_PLAN_DATA.*$",
                user,
            )
            request_data = json.loads(match.group(1) if match else user)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("Mock provider input must be a JSON route plan.") from error
        route_plan = request_data.get("plan", request_data)
        narrative = self._build_narrative(route_plan)
        if self.mode in {"faulty", "faulty_number"}:
            narrative.summary += " Estimated delay: 999 hours."
        if self.mode in {"faulty", "faulty_place"}:
            narrative.dispatcher_actions.append("reroute through Phoenix.")
        if self.mode == "faulty_route_id":
            narrative.dispatcher_actions.append("review route-999.")
        if self.mode == "faulty_safe":
            narrative.dispatcher_actions.append("this route is safe to travel.")
        text = narrative.model_dump_json()
        return ProviderResponse(
            text=text,
            tokens=len(system.split()) + len(user.split()) + len(text.split()),
            latency_ms=(time.perf_counter() - started) * 1000,
            input_tokens=len(system.split()) + len(user.split()),
            output_tokens=len(text.split()),
            finish_reason="stop",
        )

    @staticmethod
    def _build_narrative(route_plan: dict) -> BriefingNarrative:
        recommended_route_id = route_plan["recommendedRouteId"]
        recommended_route = next(
            (route for route in route_plan["routes"] if route["id"] == recommended_route_id),
            None,
        )
        if recommended_route is None:
            raise ValueError("Route plan has no route matching recommendedRouteId.")

        route_risks = expected_route_risks(route_plan)
        recommended_risks = next(
            item for item in route_risks if item["route_id"] == recommended_route_id
        )
        has_forecast_gap = any(
            checkpoint.get(field) is None
            for route in route_plan["routes"]
            for checkpoint in route["checkpoints"]
            for field in ("windMph", "rainInHr", "snowInHr")
        )
        gap_intro = (
            "Forecast gaps: required weather data is unavailable."
            if has_forecast_gap
            else "Forecast gaps: none."
        )
        if recommended_risks["no_travel_count"]:
            risk_text = "The recommended route has No Travel risk."
            action = "hold dispatch for review."
        elif recommended_risks["severe_count"]:
            risk_text = "The recommended route has Severe risk."
            action = "review Severe checkpoints before dispatch."
        elif any(
            checkpoint.get("risk") == "High"
            for checkpoint in recommended_route["checkpoints"]
        ):
            risk_text = "The recommended route has High risk."
            action = "brief the driver on elevated-risk checkpoints."
        else:
            risk_text = "The recommended route has no elevated risk in the plan."
            action = "monitor checkpoint forecasts before dispatch."

        return BriefingNarrative(
            summary="{} {} {}".format(gap_intro, recommended_route_id, risk_text),
            dispatcher_actions=[action],
        )


class AnthropicProvider:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for the Anthropic provider.")
        self._model = model or os.getenv("ANTHROPIC_MODEL")
        if not self._model:
            raise ValueError("ANTHROPIC_MODEL is required for the Anthropic provider.")
        try:
            import anthropic
        except ImportError as error:
            raise RuntimeError("Install the anthropic package to use this provider.") from error
        self._api_error_type = anthropic.APIError
        self._client = anthropic.Anthropic(
            api_key=api_key,
            timeout=PROVIDER_TIMEOUT_SECONDS,
            max_retries=0,
        )

    def generate(self, system: str, user: str) -> ProviderResponse:
        started = time.perf_counter()
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1200,
                temperature=0,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except self._api_error_type as error:
            raise ProviderRequestError("Anthropic briefing request failed.") from error
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        return ProviderResponse(
            text,
            input_tokens + output_tokens,
            (time.perf_counter() - started) * 1000,
            input_tokens,
            output_tokens,
            _normalize_finish_reason(getattr(response, "stop_reason", None)),
        )


class OpenAIProvider:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for the OpenAI provider.")
        self._model = model or os.getenv("OPENAI_MODEL")
        if not self._model:
            raise ValueError("OPENAI_MODEL is required for the OpenAI provider.")
        try:
            from openai import APIError, OpenAI
        except ImportError as error:
            raise RuntimeError("Install the openai package to use this provider.") from error
        self._api_error_type = APIError
        self._client = OpenAI(
            api_key=api_key,
            timeout=PROVIDER_TIMEOUT_SECONDS,
            max_retries=0,
        )

    def generate(self, system: str, user: str) -> ProviderResponse:
        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=1200,
            )
        except self._api_error_type as error:
            raise ProviderRequestError("OpenAI briefing request failed.") from error
        text = response.choices[0].message.content or ""
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        return ProviderResponse(
            text,
            input_tokens + output_tokens,
            (time.perf_counter() - started) * 1000,
            input_tokens,
            output_tokens,
            _normalize_finish_reason(
                getattr(response.choices[0], "finish_reason", None)
            ),
        )


class GroqProvider:
    MIN_REQUEST_INTERVAL_SECONDS = 2.1
    MAX_RATE_LIMIT_RETRIES = 3

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        api_key = api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is required for the Groq provider.")
        self._model = model or os.getenv("GROQ_MODEL")
        if not self._model:
            raise ValueError("GROQ_MODEL is required for the Groq provider.")
        try:
            self._max_tokens = int(os.getenv("GROQ_MAX_TOKENS", "4096"))
        except ValueError as error:
            raise ValueError("GROQ_MAX_TOKENS must be a positive integer.") from error
        if self._max_tokens < 1:
            raise ValueError("GROQ_MAX_TOKENS must be a positive integer.")
        self._api_key = api_key
        self._last_request_at = None
        try:
            from openai import APIError, OpenAI
        except ImportError as error:
            raise RuntimeError("Install the openai package to use the Groq provider.") from error
        self._api_error_type = APIError
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            timeout=GROQ_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
        )

    def generate(self, system: str, user: str) -> ProviderResponse:
        request_latency_ms = 0.0
        wait_events = []
        for attempt in range(self.MAX_RATE_LIMIT_RETRIES + 1):
            if self._last_request_at is not None:
                elapsed = time.monotonic() - self._last_request_at
                if elapsed < self.MIN_REQUEST_INTERVAL_SECONDS:
                    self._wait(
                        self.MIN_REQUEST_INTERVAL_SECONDS - elapsed,
                        "minimum request interval",
                        wait_events,
                    )
            self._last_request_at = time.monotonic()
            started = time.perf_counter()
            try:
                request_options = {
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                    "max_tokens": self._max_tokens,
                }
                if "gpt-oss" in self._model.lower():
                    request_options["reasoning_effort"] = "low"
                response = self._client.chat.completions.create(
                    **request_options, timeout=GROQ_REQUEST_TIMEOUT_SECONDS
                )
                request_latency_ms += (time.perf_counter() - started) * 1000
                break
            except self._api_error_type as error:
                request_latency_ms += (time.perf_counter() - started) * 1000
                status_code = getattr(error, "status_code", None)
                if (
                    status_code == 429
                    and attempt < self.MAX_RATE_LIMIT_RETRIES
                ):
                    self._wait(
                        self._rate_limit_retry_delay(error, attempt),
                        "HTTP 429 retry {}".format(attempt + 1),
                        wait_events,
                    )
                    continue
                if isinstance(error, TimeoutError) or "timeout" in type(error).__name__.lower():
                    raise TimeoutError(
                        "Groq briefing request exceeded the {} second timeout.".format(
                            GROQ_REQUEST_TIMEOUT_SECONDS
                        )
                    ) from error
                body = getattr(error, "body", None)
                details = body.get("error", {}) if isinstance(body, dict) else {}
                message = details.get("message") if isinstance(details, dict) else None
                code = details.get("code") if isinstance(details, dict) else None
                safe_message = str(message or "").replace(
                    self._api_key, "[REDACTED]"
                )[:300]
                error_details = ", ".join(
                    item
                    for item in (str(code) if code else "", safe_message)
                    if item
                )
                raise ProviderRequestError(
                    "Groq briefing request failed ({}{}).".format(
                        "HTTP {}".format(status_code)
                        if status_code is not None
                        else "connection error",
                        ", " + error_details if error_details else "",
                    )
                ) from error

        text = response.choices[0].message.content or ""
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        return ProviderResponse(
            text,
            input_tokens + output_tokens,
            request_latency_ms,
            input_tokens,
            output_tokens,
            _normalize_finish_reason(
                getattr(response.choices[0], "finish_reason", None)
            ),
            sum(event["duration_ms"] for event in wait_events),
            wait_events,
        )

    @staticmethod
    def _rate_limit_retry_delay(error, attempt):
        response = getattr(error, "response", None)
        headers = response.headers if response is not None else {}
        for header in ("retry-after", "x-ratelimit-reset-requests"):
            value = headers.get(header)
            if value:
                normalized = value[:-1] if value.endswith("s") else value
                try:
                    return min(
                        max(float(normalized), 0.0),
                        MAX_RATE_LIMIT_WAIT_SECONDS,
                    )
                except ValueError:
                    pass
        return min(
            float(2 ** (attempt + 1)),
            MAX_RATE_LIMIT_WAIT_SECONDS,
        )

    @staticmethod
    def _wait(duration, reason, wait_events):
        wait_seconds = min(max(duration, 0.0), MAX_RATE_LIMIT_WAIT_SECONDS)
        if not wait_seconds:
            return
        _logger.info(
            "Groq provider wait reason=%s duration_seconds=%.3f",
            reason,
            wait_seconds,
        )
        time.sleep(wait_seconds)
        wait_events.append(
            {
                "reason": reason,
                "duration_ms": wait_seconds * 1000,
            }
        )


class GeminiProvider:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for the Gemini provider.")
        self._model = model or os.getenv("GEMINI_MODEL")
        if not self._model:
            raise ValueError("GEMINI_MODEL is required for the Gemini provider.")
        try:
            from google import genai
            from google.genai import errors, types
        except ImportError as error:
            raise RuntimeError("Install the google-genai package to use Gemini.") from error
        self._api_error_type = errors.APIError
        self._types = types
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(PROVIDER_TIMEOUT_SECONDS * 1000)
            ),
        )

    def generate(self, system: str, user: str) -> ProviderResponse:
        started = time.perf_counter()
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user,
                config=self._types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    temperature=0,
                    max_output_tokens=1200,
                ),
            )
        except self._api_error_type as error:
            raise ProviderRequestError(
                "Gemini briefing request failed (HTTP {}, {}).".format(
                    error.code, error.status
                )
            ) from error
        text = response.text or ""
        usage = response.usage_metadata
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        return ProviderResponse(
            text,
            input_tokens + output_tokens,
            (time.perf_counter() - started) * 1000,
            input_tokens,
            output_tokens,
            _normalize_finish_reason(
                getattr(response.candidates[0], "finish_reason", None)
                if getattr(response, "candidates", None)
                else None
            ),
        )


def _normalize_finish_reason(reason):
    if reason is None:
        return None
    return str(getattr(reason, "name", reason))


def get_provider(name: Optional[str] = None) -> Provider:
    configured_name = name or os.getenv("LLM_PROVIDER")
    if not configured_name and (
        os.getenv("RENDER", "").lower() == "true"
        or os.getenv("DEBUG", "True").lower() not in {"1", "true", "yes", "on"}
    ):
        raise ProviderConfigurationError(
            "LLM_PROVIDER must be configured in production."
        )
    provider_name = (configured_name or "mock").strip().lower()
    if provider_name == "mock":
        return MockProvider()
    if provider_name == "anthropic":
        return AnthropicProvider()
    if provider_name == "openai":
        return OpenAIProvider()
    if provider_name == "groq":
        return GroqProvider()
    if provider_name == "gemini":
        return GeminiProvider()
    raise ValueError(
        "LLM_PROVIDER must be 'mock', 'anthropic', 'openai', 'groq', or 'gemini'."
    )
