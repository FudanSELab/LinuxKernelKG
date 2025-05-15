# coding: utf-8
from langchain.prompts import PromptTemplate
import json

class extractTripleOpenPrompt:

    template = """{{
    "instructions": "You are an expert in openIE tasks, and also an expert in the Linux kernel.
        Given a Linux kernel feature description (feature_description) and related contextual title information (parents),
        Your task is to: extract ABSOLUTELY ALL possible relation triples (triples). a triple should be in the format [head, relation, tail, type_of_tail].
        The 'parents' list describe a hierarchical structure of the feature, where the leftmost title is the most general title, and the rightmost title is the most specific title.
        Here are a few guidelines to help you:
        1. the head should be a noun phrase that represents the subject of the relation. Also,
            the head should be a concept or term that is relevant to the Linux kernel.
        2. the tail can be of one of the two types:
            (1) A noun phrase that represents the object of the relation (noun).
            (2) An adjective or adverb phrase, or a clause that describes a property or characteristic of the head (adj/adv/clause).
            You should output the type of the tail in the last element of the triple.
        3. The phrases located at the beginning of the feature description and before the colon is usually the name of the module to which the feature belongs.
            In other words, the changes usually happen within the module.
        4. Make sure the triples you extract are meaningful and precise.
        You can refer to the examples field for guidance.",
    "examples": [
    {{
        "input": {{
            "parents": ["Memory management"]
            "feature_description": "Prohibit the last subpage from reusing the entire large folio",
        }},
        "output": {{
            "triples": [["page", "uses", "folio", "noun"]]
        }}
    }},
    {{
        "input": {{
            "parents": ["Architectures", "POWERPC"]
            "feature_description": "Make ELFv2 ABI the default for 64-bit big-endian kernel builds",
        }},
        "output": {{
            "triples": [["ELFv2 ABI", "is default for", "64-bit big-endian kernel builds", "noun"]]
        }}
    }},
    {{
        "input": {{
            "parents": ["Various core changes"]
            "feature_description": "kconfig: add make localyesconfig option",
        }},
        "output": {{
            "triples": [["make localyesconfig", "is an option of", "kconfig", "noun"]]
        }}
    }},
    {{
        "input": {{
            "parents": ["Memory management"],
            "feature_description": "Memory cgroup controller: Reclaim memory from nodes in round-robin order",
        }},
        "output": {{
            "triples": [["Memory cgroup controller", "reclaims", "memory", "noun"],
                       ["memory reclaim", "is done in", "round-robin order", "noun"]]
        }}
    }},
    {{
        "input": {{
            "parents": ["Memory management"],
            "feature_description": "Add Uacce (Unified/User-space-access-intended Accelerator Framework). Von Neumann architecture is not good at general data manipulation so there are more and more heterogeneous processors such as encryption/decryption accelerators TPUs or EDGE processors.",
        }},
        "output": {{
            "triples": [["Uacce", "is abbreviation of", "Unified/User-space-access-intended Accelerator Framework", "noun"],
                        ["Von Neumann architecture", "is not good at", "general data manipulation", "noun"],
                        ["TPUs", "is a type of", "heterogeneous processors", "noun"],
                        ["EDGE processors", "is a type of", "heterogeneous processors", "noun"],
                        ["Uacce", "is related to", "encryption/decryption accelerators", "noun"]]
        }}
    }},
    {{
        "input": {{
            "parents": ["Memory management"],
            "feature_description": "Add a new software tag-based mode to KASAN. The plan is to implement HWASan for the kernel with the incentive that it's going to have comparable to KASAN performance but in the same time consume much less memory trading that off for somewhat imprecise bug detection and being supported only for arm64."
        }},
        "output": {{
            "triples": ["bug detection", "is", "somewhat imprecise for HWASan", "adj/adv/clause"],
                        ["KASAN performance", "is comparable to", "HWASan performance", "noun"],
                        ["KASAN", "consumes less memory than", "HWASan", "noun"]]

        }}
    }},
    {{
        "input": {{
            "parents": ["Core (various)", "Scheduler"],
            "feature_description": "Energy Model improvements: fix & refine all the energy fairness metrics (PELT) and remove the conservative threshold requiring 6% energy savings to migrate a task. Doing this improves power efficiency for most workloads and also increases the reliability of energy-efficiency scheduling (recommended LWN article)"
        }},
        "output": {{
            "triples": [["Energy Model", "improves", "power efficiency", "noun"],
                        ["energy fairness metrics", "is a type of", "PELT", "noun"],
                        ["conservative threshold", "requires", "6% energy savings to migrate a task", "adj/adv/clause"],
                        ["energy-efficiency scheduling", "is recommended by", "LWN article", "noun"]]
        }}
    }},
    {{
        "input": {{
            "parents": [],
            "feature_description": ""
        }},
        "output": {{
            "triples": []
        }}
    }}
    ],
    "input": {{
        "parents": "{parents}"
        "feature_description": "{feature_description}"
    }}
}}
"""

    prompt_template_extract = PromptTemplate(template=template, input_variables=["feature_description", "parents"])

    def __init__(self, feature_description, parents):
        self.feature_description = feature_description
        self.parents = parents

    def format(self):
        return self.prompt_template_extract.format(
            feature_description = self.feature_description,
            parents = self.parents
        )


# 测试代码

# test_obj = {
#     'feature_description': 'test',
#     'commits': "abc"
# }

# print(extractPrompt(**test_obj).format())