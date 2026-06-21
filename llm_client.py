import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

PROVIDERS = {
    "groq": {
        "base_url": os.getenv(
            "GROQ_BASE_URL",
            "https://api.groq.com/openai/v1",
        ),
        "api_key_env": "GROQ_API_KEY",
        "default_model": os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
    },
    "gemini": {
        "base_url": os.getenv(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        ),
        "api_key_env": "GEMINI_API_KEY",
        "default_model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    },
    "glm": {
        "base_url": os.getenv(
            "GLM_BASE_URL",
            "https://api.z.ai/api/paas/v4",
        ),
        "api_key_env": "GLM_API_KEY",
        "default_model": os.getenv("GLM_MODEL", "GLM-4.5-Flash"),
    },
}

class ProviderConfigError(ValueError):
    pass


def get_client(provider=None):
    provider = (provider or os.getenv("DEFAULT_PROVIDER", "groq")).lower()
    config = PROVIDERS.get(provider)
    if not config:
        raise ProviderConfigError(f"Unknown provider: {provider}")

    api_key = os.getenv(config["api_key_env"])
    if not api_key:
        raise ProviderConfigError(f"{config['api_key_env']} not set in .env")

    client = OpenAI(
        api_key=api_key,
        base_url=config["base_url"],
    )
    return client, provider


def get_model(provider=None):
    provider = (provider or os.getenv("DEFAULT_PROVIDER", "groq")).lower()
    return PROVIDERS.get(provider, PROVIDERS["groq"])["default_model"]


def get_available_providers():
    providers = []
    for provider, config in PROVIDERS.items():
        if os.getenv(config["api_key_env"]):
            providers.append(provider)

    if not providers:
        raise ProviderConfigError("No LLM API keys configured in .env")

    return providers


def get_provider_sequence(requested_provider=None):
    if requested_provider:
        ordered = [requested_provider.lower()]
    else:
        configured_order = os.getenv("PROVIDER_ORDER", "groq,gemini,glm")
        ordered = [
            provider.strip().lower()
            for provider in configured_order.split(",")
            if provider.strip()
        ]

    result = []
    for provider in ordered:
        if provider in result:
            continue
        config = PROVIDERS.get(provider)
        if config and os.getenv(config["api_key_env"]):
            result.append(provider)

    return result
