from enum import Enum

class LLMType(Enum):
    """LLM类型枚举"""
    OPENAI = "openai"
    DEEPSEEK = "deepseek"

# 大模型配置字典
LLM_CONFIG = {
    LLMType.OPENAI: {
        "api_key": "sk-OIA8e1b5f9e53736bf8a045d17bb205403a6be38d49h7PYl",
        "base_url": "https://api.gptsapi.net/v1",
        "model": "gpt-4o-mini"
    },
    LLMType.DEEPSEEK: {
        "api_key": "sk-c875aefe59f5412a919c431bac6c7cea",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat"
    }
}