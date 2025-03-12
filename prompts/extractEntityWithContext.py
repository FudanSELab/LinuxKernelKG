# coding: utf-8
from langchain.prompts import PromptTemplate
import json

class extractEntityWithContextPrompt:

    template = """{{
    "instructions": "You are an expert in Named Entity Recognition (NER) tasks and also an expert in the Linux kernel.
      Given a Linux kernel feature description (feature_description) and related contextual title information (h1, h2), 
      your task is to: extract ABSOLUTELY ALL possible concept entities (entities), and describe why these entities are reasonable. 
      IMPORTANT: ONLY extract entities that appear in the feature_description text. Return your answer as a JSON format string.

    Entity extraction rules (extract ALL possible entities FROM FEATURE_DESCRIPTION ONLY):
    1. BE EXTREMELY THOROUGH - extract EVERY possible entity, even if you're uncertain. It is CRITICAL to not miss any entities.
    2. Extract BOTH compound terms AND their components from feature_description. For example, if 'memory management' appears, extract both 'memory management', 'memory', and 'management'.
    3. Focus on ALL NOUNS, NOUN PHRASES, TECHNICAL TERMS, ABBREVIATIONS, and DOMAIN-SPECIFIC CONCEPTS.
    4. ALWAYS split compound terms with underscores, hyphens, or camelCase and include both the full term AND each individual component as separate entities.
    5. Consider ALL technical jargon, system components, hardware elements, software concepts, and kernel-related terminology as potential entities.
    6. For any technical term, also extract its variations that appear in the text (plural forms, abbreviated forms, etc.)
    7. When you see numbers or identifiers that might represent versions, models, or specifications, include them as entities.
    8. REMEMBER: It is better to extract too many entities than to miss important ones. When in doubt, ALWAYS include it.
    9. Avoid extracting standalone adjectives or adverbs unless they are part of a term (e.g., 'inline processing' is valid, but not 'inline' alone)
    10. DO NOT extract common verbs and generic action words like: 'add', 'support', 'implement', 'enable', 'check', 'export', 'create', 'improve', 'optimize', 'fix', 'allow', 'make', 'use', 'handle', 'provide'
    11. DO NOT extract generic descriptive words like: 'new', 'better', 'faster', 'improved', 'enhanced', 'basic', 'simple'
    You can refer to the examples field for guidance.",
    "examples": [{{
        "input": {{
            "h1": "Networking",
            "h2": "Protocols",
            "feature_description": "Fix packet_fanout implementation to properly handle protocol arrays in the queue"
        }},
        "output": {{
            "reason": "I've extracted all possible entities from the feature description, being extremely thorough. 'Packet_fanout' is a networking feature, so I extracted both the compound term and its components. 'Implementation', 'protocol', 'arrays', 'protocol arrays', and 'queue' are all technical concepts relevant to the feature. I even included 'handle' as it could be considered a technical operation in this context.",
            "entities": ["packet_fanout", "packet", "fanout", "implementation", "properly", "handle", "protocol", "arrays", "protocol arrays", "queue", "the queue"]
        }}
    }}, {{
        "input": {{
            "h1": "Processors",
            "h2": "Intel",
            "feature_description": "Add idle state support for Intel Comet Lake PCH"
        }},
        "output": {{
            "reason": "I've extracted absolutely all possible entities from the feature description. 'Idle state' refers to a processor power state, so I extracted both the compound term and its components. 'Support' could be considered a technical concept in this context. 'Intel', 'Comet Lake', 'Intel Comet Lake', 'PCH' are all hardware-related entities. I've been extremely thorough to ensure no potential entity is missed.",
            "entities": ["idle state", "idle", "state", "support", "Intel", "Comet Lake", "Intel Comet Lake", "Comet", "Lake", "PCH", "Intel Comet Lake PCH"]
        }}
    }}, {{
        "input": {{
            "h1": "File Systems",
            "h2": "Ext4",
            "feature_description": "Optimize inode allocation to improve performance on large directories"
        }},
        "output": {{
            "reason": "I've extracted all possible entities from the feature description. 'Inode allocation' is a file system concept, so I extracted both the compound term and its components. 'Optimize', 'performance', 'large directories', 'directories' are all relevant technical terms.",
            "entities": ["inode allocation", "inode", "allocation", "optimize", "performance", "large directories", "large", "directories"]
        }}
    }}, {{
        "input": {{
            "h1": "Security",
            "h2": "Encryption",
            "feature_description": "Implement AES-256 encryption for secure data transmission"
        }},
        "output": {{
            "reason": "I've extracted all possible entities from the feature description. 'AES-256 encryption' is a security concept, so I extracted both the compound term and its components. 'Secure data transmission', 'secure', 'data', 'transmission' are all relevant technical terms.",
            "entities": ["AES-256 encryption", "AES-256", "encryption", "secure data transmission", "secure", "data", "transmission"]
        }}
    }}, {{
        "input": {{
            "h1": "Virtualization",
            "h2": "KVM",
            "feature_description": "Enhance virtual machine scheduling to reduce latency"
        }},
        "output": {{
            "reason": "I've extracted all possible entities from the feature description. 'Virtual machine scheduling' is a virtualization concept, so I extracted both the compound term and its components. 'Enhance', 'reduce latency', 'latency' are all relevant technical terms.",
            "entities": ["virtual machine scheduling", "virtual machine", "scheduling", "enhance", "reduce latency", "reduce", "latency"]
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