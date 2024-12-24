from openai import OpenAI
import logging
import time
from utils.logger import setup_logger

# 配置 deepseek
deepseek_api_key = 'sk-c875aefe59f5412a919c431bac6c7cea'

class deepseek:

    def __init__(self):
        self.client = OpenAI(api_key=deepseek_api_key, base_url="https://api.deepseek.com")
        self.logger = setup_logger("deepseek", logging.DEBUG, console_output=False, file_output=True)

    def get_response(self, prompt):

        self.logger.debug(f"invoking deepseek with prompt:\n{prompt}")

        while True:
            try:
                response = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant"},
                        {"role": "user", "content": prompt},
                    ],
                    stream=False
                )
                if response.choices[0].finish_reason != "stop":
                    self.logger.error(f"Request failed in deepseek.get_response(), retrying in 10 seconds: {response.choices[0].finish_reason}")
                    time.sleep(10)
                    continue
                break
            except Exception as e:
                self.logger.error(f"Request failed in deepseek.get_response(), retrying in 10 seconds: {e}")
                time.sleep(10)

        self.logger.debug(f"deepseek response:\n{response.choices[0].message.content}")

        return response.choices[0].message.content