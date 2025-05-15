# coding: utf-8
from langchain.prompts import PromptTemplate
import json

class ngramClassifyRelationPrompt: 

    template = """{{
    "instructions": "You are an expert in openIE tasks, and also an expert in the Linux kernel.
        Given a list of pair of words (head, tail), where the tail is either a prefix or a suffix of the head,
        Your task is to: classify the relation between the head and tail.
        The relation can be one of the following types:
        1. IS_INSTANCE_OF: 
            + Indicates that a specific entity is a concrete member or instantiation of a more general class/category.
            + Represents an "is-a" or "inheritance" relationship (individual → class).
            + Used for taxonomic hierarchies (e.g., classifying instances).
        2. IS_ASPECT_OF:
            + Indicates that an entity represents a specific perspective, feature, or dimension of another entity.
            + Represents a "has-a" or "composition" relationship (class → aspect).
            + Used for cross-cutting concerns (e.g., functionality, attributes, or viewpoints).
        3. REFERENCE: The relation between the head and tail is neither of the above.
        It is ensured that the head and tail are both related to the Linux kernel.
        
        If the relation is not clear, or either head or tail is not a noun, or you are not sure about the
        meaning of the head and tail, you should choose REFERENCE.
        
        Hint: when the tail is a suffix of the head, the relation is more likely to be IS_INSTANCE_OF or REFERENCE;
        when the tail is a prifix of the head, the relation is more likely to be IS_ASPECT_OF or REFERENCE.

        The output should be in JSON format. You can refer to the examples field for guidance.",
    "examples": [
    {{
        "input": [
            ["640x480 SBGGR8 mode", "640x480"],
            ["Broadcom 43xx based wireless cards", "wireless cards"],
            ["dprintk and dynamic printk", "dynamic printk"],
            ["driver support for audioreach solution", "driver support"],
        ],
        "output": [
            "REFERENCE",
            "IS_INSTANCE_OF",
            "REFERENCE",
            "IS_INSTANCE_OF",
        ]
    }},
    {{
        "input": [
            ["concurrent transmission of data", "concurrent transmission"],
            ["controller reset support", "controller"],
            ["cpufreq driver interface", "cpufreq driver"],
            ["frames beyond 8192 byte size", "frames"],
            ["gpio driver support", "gpio driver"],
        ],
        "output": [
            "IS_INSTANCE_OF",
            "IS_ASPECT_OF",
            "IS_ASPECT_OF",
            "IS_INSTANCE_OF",
            "REFERENCE",
        ]
    }},
    {{
        "input": [
            ["ArrowLake-H platform", "platform"],
            ["BH workqueue conversion", "conversion"],
            ["6% energy savings to migrate a task", "task"],
            ["64-bit data integrity", "64-bit"],
            ["ARM architecture", "architecture"],
            ["Ayaneo Air Plus 7320u", "7320u"],
            ["64-bit data integrity", "integrity"]
            ["ACPI table", "ACPI"],
            ["ACPI table", "table"],
        ],
        "output": [
            "IS_INSTANCE_OF",
            "IS_INSTANCE_OF",
            "REFERENCE",
            "REFERENCE",
            "IS_INSTANCE_OF",
            "REFERENCE",
            "IS_INSTANCE_OF",
            "IS_ASPECT_OF",
            "IS_INSTANCE_OF",
        ]
    }}
    ],
    "input": {input},
}}
"""

    prompt_template_classify = PromptTemplate(template=template, input_variables=["input"])

    def __init__(self, input):
        self.input = input

    def format(self):
        return self.prompt_template_classify.format(
            input=json.dumps(self.input, ensure_ascii=False, indent=4)
        )
    