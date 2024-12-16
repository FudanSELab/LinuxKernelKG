# coding: utf-8
from langchain.prompts import PromptTemplate
import json

class fusionPrompt:

    template = """{{
    "instructions": "你是一个知识图谱专家，同时也是 linux 内核的专家。给你一个从 linux 内核中抽取出的实体列表 entities，你的任务是识别其中的同义词实体并将它们分组。同义词包括：1. 大小写不同的相同词；2. 缩写和全称；3. 表达相同概念的不同说法。用json格式字符串返回你的回答。你可以参考 examples 字段给出的例子。",
    "examples": [{{
        "input": {{
            "entities": ["Virtual Memory", "VM", "virtual memory", "Memory Management", "memory management", "Page Fault Handler", "page fault handling", "THP", "Transparent Huge Pages", "Transparent HugePages", "Memory Pool", "memory pools"]
        }},
        "output": [
            {{
                "canonical": "Virtual Memory",
                "aliases": ["VM", "virtual memory"]
            }},
            {{
                "canonical": "Memory Management",
                "aliases": ["memory management"]
            }},
            {{
                "canonical": "Page Fault Handler",
                "aliases": ["page fault handling"]
            }},
            {{
                "canonical": "Transparent Huge Pages",
                "aliases": ["THP", "Transparent HugePages"]
            }},
            {{
                "canonical": "Memory Pool",
                "aliases": ["memory pools"]
            }}
        ]
    }}],
    "input": {{
        "entities": {entities}
    }}
}}
"""

    def __init__(self, entities=None):
        self.entities = entities

    def format(self):
        return self.template.format(
            entities=json.dumps(self.entities, ensure_ascii=False)
        )