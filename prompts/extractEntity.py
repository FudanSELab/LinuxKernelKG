# coding: utf-8
from langchain.prompts import PromptTemplate
import json

class extractEntityPrompt:

    template = """{{
    "instructions": "你是一个命名实体抽取 (NER) 任务的专家，同时也是 linux 内核的专家。给你一个 linux 内核特性的描述 (feature_description)、对应的若干 commit 的标题和提交信息 (commits可能为空)。你的任务是：根据这些信息提取出在 linux 内核中涉及到的和这个特性相关的概念实体 (entities)，以及描述为什么这些实体是合理的。用英语回答。用json格式字符串返回你的回答。你可以参考 examples 字段给出的例子。",
    "examples": [{{
        "input": {{
            "feature_description": "Prohibit the last subpage from reusing the entire large folio",
            "commits": ""
        }},
        "output": {{
            "entities": ["folio"],
            "reason": "The entity 'folio' is the only entity in the feature description."
        }}
    }}],
    "input": {{
        "feature_description": "{feature_description}",
        "commits": {commits},
    }}
}}
"""

    prompt_template_extract = PromptTemplate(template=template, input_variables=["feature_description", "commits"])

    def __init__(self, feature_description, commits):
        self.feature_description = feature_description
        self.commits = commits

    def format(self):
        return self.prompt_template_extract.format(
            feature_description = self.feature_description,
            commits = json.dumps(self.commits, ensure_ascii=False, indent=None),
        )


# 测试代码

# test_obj = {
#     'feature_description': 'test',
#     'commits': "abc"
# }

# print(extractPrompt(**test_obj).format())