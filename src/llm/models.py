"""LLM provider/model registry."""
from enum import Enum
from pydantic import BaseModel
from typing import Tuple, List


class ModelProvider(str, Enum):
    GROQ     = "Groq"
    DEEPSEEK = "DeepSeek"


class LLMModel(BaseModel):
    display_name: str
    model_name: str
    provider: ModelProvider

    def to_choice_tuple(self) -> Tuple[str, str, str]:
        return (self.display_name, self.model_name, self.provider.value)

    def is_custom(self) -> bool:
        return False

    def has_json_mode(self) -> bool:
        return True

    def is_deepseek(self) -> bool:
        return self.provider == ModelProvider.DEEPSEEK

    def is_gemini(self) -> bool:
        return False

    def is_ollama(self) -> bool:
        return False


_GROQ_MODELS = [
    LLMModel(display_name="Llama 3.3 70B (Groq)",   model_name="llama-3.3-70b-versatile", provider=ModelProvider.GROQ),
    LLMModel(display_name="Llama 3.1 8B (Groq)",    model_name="llama-3.1-8b-instant",    provider=ModelProvider.GROQ),
]

_DEEPSEEK_MODELS = [
    LLMModel(display_name="DeepSeek V4 Flash",       model_name="deepseek-v4-flash",       provider=ModelProvider.DEEPSEEK),
    LLMModel(display_name="DeepSeek V4 Pro",         model_name="deepseek-v4-pro",         provider=ModelProvider.DEEPSEEK),
]

_ALL_MODELS = _GROQ_MODELS + _DEEPSEEK_MODELS

LLM_ORDER:       List[Tuple[str, str, str]] = [m.to_choice_tuple() for m in _ALL_MODELS]
OLLAMA_LLM_ORDER: List[Tuple[str, str, str]] = []


def get_model_info(model_name: str, model_provider: str) -> LLMModel | None:
    for m in _ALL_MODELS:
        if m.model_name == model_name and m.provider.value == model_provider:
            return m
    return None


def find_model_by_name(model_name: str) -> LLMModel | None:
    for m in _ALL_MODELS:
        if m.model_name == model_name:
            return m
    return None


def get_model(model_name: str, model_provider: str, api_keys=None):
    import os
    if model_provider == ModelProvider.DEEPSEEK.value:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_name,
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )
    from langchain_groq import ChatGroq
    return ChatGroq(model=model_name, api_key=os.getenv("GROQ_API_KEY"))
