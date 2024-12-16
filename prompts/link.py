# coding: utf-8
from langchain.prompts import PromptTemplate
import json

class linkPrompt:

    template = """{{
    "instructions": "你是一个知识图谱专家，同时也是 linux 内核的专家。给你一个可能在 linux 内核中出现的概念的列表 entities 以及一个由专家所提供的概念列表 entities_expert, 你的任务是为 entities 中的每个概念找到 entities_expert 中与之关系最接近的概念, 或报告找不到匹配概念。用json格式字符串返回你的回答。你可以参考 examples 字段给出的例子。",
    "examples": [{{
        "input": {{
            "entities": ["KSM", "madvise", "prctl", "smaps", "zeropages", "kthreadd"],
            "entities_expert": ["Zone Management", "Memory Control Policies", "Copy-On-Write", "Virtual Memory Allocation", "Memory Protection", "Page Fault", "Memory Initialization", "Shared Memory Management", "Failure Detecting & Handling", "Performance Monitoring", "Debug & Test", "Memory Mapping", "Memory Re-mapping", "Reverse Mapping", "Page Isolation", "Page Migration", "Hotplug", "Kernel Same-page Merging", "Page Ownership Management", "Memory Pool Management", "Huge Pages Management", "Page Writeback", "Page I/O", "Workingset Management", "Page Allocation", "Contiguous Memory Allocation", "Memory Slab Allocation", "DMA", "highmem", "Memory Compaction", "Memory Swapping", "Direct Mapping Management", "Concurrency Control (Locks)"]
        }},
        "output": [
                ["KSM", "Kernel Same-page Merging"],
                ["madvise", "Memory Control Policies"],
                ["prctl", "Memory Control Policies"],
                ["smaps", "Memory Mapping"],
                ["zeropages", "Page Allocation"],
                ["kthreadd", "null"]
        ]
    }}],
    "input": {{
        "entities": {entities},
        "entities_expert": {entities_expert}
    }}
}}
"""

    def __init__(self, entities=None, entities_expert=None):
        self.entities = entities
        self.entities_expert = entities_expert

    def format(self):
        return self.template.format(
            entities=json.dumps(self.entities, ensure_ascii=False),
            entities_expert=json.dumps(self.entities_expert, ensure_ascii=False)
        )