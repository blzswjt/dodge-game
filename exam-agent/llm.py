"""
LLM 客户端封装 - OpenAI 兼容接口
"""
import os
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv("LLM_API_KEY"),
            base_url=os.getenv("LLM_BASE_URL"),
        )
    return _client


def get_model() -> str:
    return os.getenv("LLM_MODEL", "qwen-plus-latest")


def chat(messages: list[dict], temperature: float = 0.3) -> str:
    """同步调用 LLM，返回完整文本"""
    client = get_client()
    response = client.chat.completions.create(
        model=get_model(),
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content


def chat_stream(messages: list[dict], temperature: float = 0.3):
    """流式调用 LLM，逐步 yield 文本片段"""
    client = get_client()
    stream = client.chat.completions.create(
        model=get_model(),
        messages=messages,
        temperature=temperature,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
