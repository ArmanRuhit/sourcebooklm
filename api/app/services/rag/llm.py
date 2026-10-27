"""Chat model factory - one env switch for OpenAI and DeepSeek."""

from langchain_core.language_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.config import settings


class ChatConfigError(RuntimeError):
    """Raised when the configured provider has no usable API key."""


def _usable_key(key: str | None) -> str:
    cleaned = (key or "").strip()
    if not cleaned or cleaned.startswith("sk-..."):
        raise ChatConfigError(
            f"{settings.chat_provider.upper()}_API_KEY is not configured; "
            "add a real key to api/.env to generate answers"
        )
    return cleaned


def model_name() -> str:
    """Return the configured model name for persistence and UI display."""
    if settings.chat_provider == "deepseek":
        return settings.deepseek_chat_model
    return settings.openai_chat_model


def get_chat_model() -> BaseChatModel:
    """Build the streaming chat model for the configured provider."""
    if settings.chat_provider == "deepseek":
        return ChatDeepSeek(
            model=settings.deepseek_chat_model,
            api_key=SecretStr(_usable_key(settings.deepseek_api_key)),
            streaming=True,
        )

    return ChatOpenAI(
        model=settings.openai_chat_model,
        api_key=SecretStr(_usable_key(settings.openai_api_key)),
        streaming=True,
    )
