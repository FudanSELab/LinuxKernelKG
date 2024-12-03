from openai import OpenAI
import logging

# 配置 deepseek
deepseek_api_key = 'sk-c875aefe59f5412a919c431bac6c7cea'

logger = logging.getLogger("extractor")

class deepseek:

    def __init__(self):
        self.client = OpenAI(api_key=deepseek_api_key, base_url="https://api.deepseek.com")

    def get_response(self, prompt):

        logger.debug(f"invoking deepseek with prompt:\n{prompt}")

        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a helpful assistant"},
                {"role": "user", "content": prompt},
            ],
            stream=False
        )

        logger.debug(f"deepseek response:\n{response}")

        return response.choices[0].message.content