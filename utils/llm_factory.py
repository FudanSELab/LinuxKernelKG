from openai import OpenAI
from config.llm_config import LLMType, LLM_CONFIG
from utils.logger import setup_logger
import logging
import time

class BaseLLM:
    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logger("llm", logging.DEBUG, console_output=False, file_output=True)

    def get_response(self, prompt: str) -> str:
        raise NotImplementedError

class DeepseekLLM(BaseLLM):
    def __init__(self, config: dict):
        super().__init__(config)
        self.client = OpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"]
        )

    def get_response(self, prompt: str) -> str:
        self.logger.debug(f"invoking deepseek with prompt:\n{prompt}")
        
        while True:
            try:
                response = self.client.chat.completions.create(
                    model=self.config["model"],
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant"},
                        {"role": "user", "content": prompt},
                    ],
                    stream=False
                )
                if response.choices[0].finish_reason != "stop":
                    self.logger.error(f"Request failed, retrying in 10 seconds: {response.choices[0].finish_reason}")
                    time.sleep(10)
                    continue
                break
            except Exception as e:
                self.logger.error(f"Request failed, retrying in 10 seconds: {e}")
                time.sleep(10)

        return response.choices[0].message.content

class OpenAILLM(BaseLLM):
    def __init__(self, config: dict):
        super().__init__(config)
        self.client = OpenAI(
            api_key=config["api_key"],
            base_url=config.get("base_url"),
            timeout=config.get("timeout", 30)
        )
        self.max_retries = config.get("max_retries", 3)
        self.retry_delay = config.get("retry_delay", 10)
        self.last_request_time = 0
        self.min_request_interval = config.get("min_request_interval", 1)

    def get_response(self, prompt: str) -> str:
        self._wait_for_rate_limit()
        
        retry_count = 0
        while retry_count < self.max_retries:
            try:
                self.logger.debug(f"Invoking OpenAI (attempt {retry_count + 1}/{self.max_retries}) with prompt:\n{prompt}")
                
                response = self.client.chat.completions.create(
                    model=self.config["model"],
                    messages=[
                        {"role": "system", "content": self.config.get("system_prompt", "You are a helpful assistant")},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=self.config.get("temperature", 0.7),
                    max_tokens=self.config.get("max_tokens", 2000),
                    stream=False
                )
                
                if not response or not response.choices:
                    raise ValueError("Empty response from OpenAI")
                
                if response.choices[0].finish_reason == "length":
                    self.logger.warning("Response was truncated due to length limits")
                elif response.choices[0].finish_reason != "stop":
                    raise ValueError(f"Unexpected finish reason: {response.choices[0].finish_reason}")
                
                self.last_request_time = time.time()
                return response.choices[0].message.content

            except Exception as e:
                retry_count += 1
                error_msg = str(e)
                
                if "rate limit" in error_msg.lower():
                    wait_time = min(self.retry_delay * (2 ** retry_count), 60)
                    self.logger.warning(f"Rate limit hit, waiting {wait_time} seconds")
                    time.sleep(wait_time)
                    continue
                    
                if retry_count < self.max_retries:
                    wait_time = self.retry_delay * (2 ** retry_count)
                    self.logger.error(f"Request failed (attempt {retry_count}/{self.max_retries}): {error_msg}")
                    self.logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"Max retries ({self.max_retries}) exceeded. Last error: {error_msg}")
                    raise Exception(f"Failed to get response after {self.max_retries} attempts: {error_msg}")

    def _wait_for_rate_limit(self):
        if self.last_request_time:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.min_request_interval:
                time.sleep(self.min_request_interval - elapsed)

class LLMFactory:
    @staticmethod
    def create_llm(llm_type: LLMType) -> BaseLLM:
        config = LLM_CONFIG[llm_type]
        
        if llm_type == LLMType.DEEPSEEK:
            return DeepseekLLM(config)
        elif llm_type == LLMType.OPENAI:
            return OpenAILLM(config)
        else:
            raise ValueError(f"Unsupported LLM type: {llm_type}") 