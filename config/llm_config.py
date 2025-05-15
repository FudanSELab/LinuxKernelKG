from enum import Enum

class LLMType(Enum):
    """LLM类型枚举"""
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    BATCH = "batch"  # 新增批量处理类型

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
    },
    LLMType.BATCH: {
        "api_key": "sk-mlrcpcghgojwbsjejwvguohuftgevaphxgcucoqvrjypjsdh",  # 使用DeepSeek的API密钥
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V3",  # 或 "deepseek-ai/DeepSeek-R1"
        "completion_window": "24h",  # 完成窗口，可设置为24h到336h
        "system_prompt": "You are a helpful assistant.",
        "temperature": 0.7,
        "max_tokens": 2000,
    }
}