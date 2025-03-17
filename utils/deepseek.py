from utils.llm_factory import LLMFactory, BaseLLM
from config.llm_config import LLMType

class deepseek(BaseLLM):
    """保持原有的 deepseek 类名以保证向后兼容"""
    def __init__(self,llm_type=LLMType.DEEPSEEK):
        # 使用工厂创建 OpenAI LLM 实例
        self._llm = LLMFactory.create_llm(llm_type)
        self.logger = self._llm.logger

    def get_response(self, prompt):
        """代理到实际的 LLM 实例"""
        return self._llm.get_response(prompt)