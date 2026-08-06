"""LLM 客户端封装：OpenAI 兼容 API，支持 reasoning 模型。"""

from openai import OpenAI

from . import config


class LLMClient:
    def __init__(self) -> None:
        if not config.OPENAI_API_KEY:
            raise RuntimeError(
                "未配置 API key：请设置环境变量 RCA_OPENAI_API_KEY 或 OPENAI_API_KEY"
            )
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
            timeout=900,
            max_retries=2,
        )
        self.model = config.MODEL

    def chat(self, messages: list[dict], max_tokens: int | None = None) -> str:
        kwargs: dict = {"model": self.model, "messages": messages}
        if config.MAX_TOKENS:
            kwargs["max_completion_tokens"] = int(config.MAX_TOKENS)
        elif max_tokens:
            kwargs["max_completion_tokens"] = max_tokens
        if config.REASONING_EFFORT:
            kwargs["reasoning_effort"] = config.REASONING_EFFORT
        resp = self.client.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()
