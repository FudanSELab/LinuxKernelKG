# coding: utf-8
from langchain.prompts import PromptTemplate
import json

class extractEntityWithContextPrompt:

    template = """{{
    "instructions": "You are an expert in Named Entity Recognition (NER) tasks and also an expert in the Linux kernel. Given a Linux kernel feature description (feature_description) and related contextual title information (h1, h2), your task is to: extract concept entities (entities) related to this feature in the Linux kernel, and describe why these entities are reasonable. Primarily extract entities from the feature_description, with h1 and h2 serving only as auxiliary contextual references. Answer in English. Return your answer as a JSON format string.

    Entity extraction rules:
    1. Capitalized word combinations are usually entities, e.g., 'CPU', 'NUMA', 'KVM', 'PCI'
    2. Terms containing a mix of letters and numbers are typically entities, e.g., 'x86_64', 'ARM64', 'IPv6'
    3. Special kernel terms like 'folio', 'slab', 'cgroup', 'namespace', etc. are also entities
    4. Hardware component names such as 'cache', 'memory', 'processor', etc. may also be entities
    5. Kernel subsystem names like 'scheduler', 'networking', 'filesystem', etc. are entities
    6. Terms that look like abbreviations or acronyms are likely entities

    You can refer to the examples field for guidance.",
    "examples": [{{
        "input": {{
            "h1": "Memory Management",
            "h2": "Page Allocation",
            "feature_description": "Prohibit the last subpage from reusing the entire large folio"
        }},
        "output": {{
            "reason": "The entities 'folio' and 'subpage' are key memory management concepts mentioned in the feature description. 'Folio' refers to a memory management structure in Linux kernel, while 'subpage' refers to a portion of a page.",
            "entities": ["folio", "subpage"]
        }}
    }}, {{
        "input": {{
            "h1": "Networking",
            "h2": "TCP/IP Stack",
            "feature_description": "Add support for TCP BBR congestion control algorithm"
        }},
        "output": {{
            "reason": "The entities extracted are 'TCP' (a networking protocol), 'BBR' (a specific algorithm name, capitalized), and 'congestion control' (a networking concept). These are all relevant to the networking subsystem of the Linux kernel.",
            "entities": ["TCP", "BBR", "congestion control"]
        }}
    }}],
    "input": {{
        "h1": "{h1}",
        "h2": "{h2}",
        "feature_description": "{feature_description}"
    }}
}}
"""

    prompt_template_extract = PromptTemplate(template=template, input_variables=["h1", "h2", "feature_description"])

    def __init__(self, h1, h2, feature_description):
        self.h1 = h1
        self.h2 = h2
        self.feature_description = feature_description

    def format(self):
        return self.prompt_template_extract.format(
            h1 = self.h1,
            h2 = self.h2,
            feature_description = self.feature_description
        )


# Test code
# test_obj = {
#     'h1': 'Memory Management',
#     'h2': 'Page Allocation',
#     'feature_description': 'Prohibit the last subpage from reusing the entire large folio'
# }
# 
# print(extractEntityWithContextPrompt(**test_obj).format()) 