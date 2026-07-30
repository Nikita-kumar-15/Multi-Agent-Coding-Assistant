"""
Centralized LLM routing for agents.

Change AGENT_MODEL_CONFIG to route agents to different providers/models.
The configuration strictly reads from the .env file as the single source of truth.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

import openai

load_dotenv()

class LLMProviderError(Exception):
    pass


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    model: str
    temperature: float = 0.2
    max_tokens: int | None = None
    fallback_route: str | None = None


LLM_PROVIDER = os.environ.get("LLM_PROVIDER")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL")

AGENT_MODEL_CONFIG: dict[str, ModelRoute] = {
    "planner":      ModelRoute(provider=LLM_PROVIDER, model=DEFAULT_MODEL, temperature=0.3),
    "coder":        ModelRoute(provider=LLM_PROVIDER, model=DEFAULT_MODEL, temperature=0.2, max_tokens=8192, fallback_route="coder_fallback"),
    "coder_fallback": ModelRoute(provider=LLM_PROVIDER, model=DEFAULT_MODEL, temperature=0.2),
    "reviewer":     ModelRoute(provider=LLM_PROVIDER, model=DEFAULT_MODEL, temperature=0.1),
    "debugger":     ModelRoute(provider=LLM_PROVIDER, model=DEFAULT_MODEL, temperature=0.1),
    "summarizer":   ModelRoute(provider=LLM_PROVIDER, model=DEFAULT_MODEL, temperature=0.2),
    "conversation": ModelRoute(provider=LLM_PROVIDER, model=DEFAULT_MODEL, temperature=0.3),
    "qa":           ModelRoute(provider=LLM_PROVIDER, model=DEFAULT_MODEL, temperature=0.1, max_tokens=8192),
    "orchestrator": ModelRoute(provider=LLM_PROVIDER, model=DEFAULT_MODEL, temperature=0.2),
    "architecture": ModelRoute(provider=LLM_PROVIDER, model=DEFAULT_MODEL, temperature=0.2),
    "fallback":     ModelRoute(provider=LLM_PROVIDER, model=DEFAULT_MODEL, temperature=0.2),
    "large_context_fallback": ModelRoute(provider=LLM_PROVIDER, model=DEFAULT_MODEL, temperature=0.2),
}


class RoutedLLM:
    """
    Thin wrapper that exposes selected model metadata and automatically
    retries when Cerebras rate limits (HTTP 429).
    """

    def __init__(self, agent_name: str, route: ModelRoute, client: Any):
        self.agent_name = agent_name
        self.provider = route.provider
        self.model_name = route.model
        self.route = route
        self.client = client

    def invoke(self, prompt: str):
        import concurrent.futures
        max_retries = 3

        for attempt in range(max_retries):
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self.client.invoke, prompt)
                    return future.result(timeout=30)
            
            except concurrent.futures.TimeoutError:
                if attempt == max_retries - 1:
                    raise LLMProviderError(f"LLM Request Timed Out (30s) after {max_retries} attempts.")
                print(f"[{self.agent_name}] LLM Request Timed Out. Retrying ({attempt+1}/{max_retries})...")
                time.sleep(2)
                continue

            except openai.APIStatusError as e:
                err = str(e).lower()
                is_payment_required = "402" in err or "payment required" in err or "payment_required" in err
                if is_payment_required:
                    raise LLMProviderError("LLM provider quota exhausted — check billing.")
                    
                is_queue_exceeded = "queue_exceeded" in err or "too_many_requests" in err
                is_rate_limit = "429" in err or "rate limit" in err
                is_context_exceeded = "context_length_exceeded" in err or ("400" in err and "context" in err)

                if is_context_exceeded:
                    print(f"[{self.agent_name}] Context length exceeded! Attempting large context fallback...")
                    fallback_route = AGENT_MODEL_CONFIG.get("large_context_fallback")
                    if fallback_route:
                        fallback_client = _build_client(fallback_route, fallback_route.temperature)
                        try:
                            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                                future = executor.submit(fallback_client.invoke, prompt)
                                return future.result(timeout=30)
                        except concurrent.futures.TimeoutError:
                            raise LLMProviderError("Context length exceeded. Large context fallback timed out (30s).")
                        except openai.APIStatusError as fallback_err:
                            raise LLMProviderError(f"Context length exceeded. Large context fallback also failed: {fallback_err}")
                        except Exception as fallback_err:
                            raise LLMProviderError(f"Context length exceeded. Large context fallback also failed: {fallback_err}")
                    else:
                        raise LLMProviderError(f"Context length exceeded and no fallback configured: {e}")

                if is_queue_exceeded:
                    wait = 120 + (60 * attempt)
                    print(f"[{self.agent_name}] Provider Queue Exceeded. Waiting {wait}s ({attempt+1}/{max_retries})...")
                    time.sleep(wait)
                elif is_rate_limit:
                    wait = 120 + (60 * attempt)
                    print(f"[{self.agent_name}] Rate limit hit. Waiting {wait}s ({attempt+1}/{max_retries})...")
                    time.sleep(wait)
                else:
                    if attempt == max_retries - 1:
                        raise LLMProviderError(f"API Error from LLM provider: {e}")
                    
                if attempt == max_retries - 1 and (is_queue_exceeded or is_rate_limit):
                    raise LLMProviderError("AI service is temporarily unavailable: All configured LLM providers are currently rate-limited. Please try again in a few minutes.")

            except Exception as e:
                if attempt == max_retries - 1:
                    raise LLMProviderError(f"Unexpected error calling LLM provider: {e}")
                time.sleep(2)





def _build_client(route: ModelRoute, temperature: float) -> Any:
    provider = route.provider.lower()

    if provider == "cerebras":
        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": route.model,
            "temperature": temperature,
            "api_key": os.getenv("CEREBRAS_API_KEY"),
            "base_url": "https://api.cerebras.ai/v1",
        }
        if route.max_tokens:
            kwargs["max_tokens"] = route.max_tokens
            
        return ChatOpenAI(**kwargs)
        
    raise ValueError(f"Unsupported LLM provider: {provider}")


def get_model(agent_name: str, temperature: float | None = None) -> RoutedLLM:
    """
    Returns the configured model for an agent.
    """

    key = agent_name.lower()

    route = AGENT_MODEL_CONFIG.get(
        key,
        AGENT_MODEL_CONFIG["fallback"],
    )

    resolved_temperature = (
        route.temperature
        if temperature is None
        else temperature
    )

    client = _build_client(
        route,
        resolved_temperature,
    )

    return RoutedLLM(
        agent_name=key,
        route=route,
        client=client,
    )

