# coding: utf-8
from langchain.prompts import PromptTemplate
import json

class extractEntityWithContextPrompt:
# 4. If compound terms are present, consider splitting them with underscores, hyphens, or camelCase and include both the full term AND each individual component as separate entities, if it makes sense contextually.

    template = """"instructions": "You are an expert in Named Entity Recognition (NER) tasks and also an expert in the Linux kernel.
      Given a Linux kernel feature description (feature_description) and related contextual title information (h1, h2), 
      your task is to: extract ABSOLUTELY ALL possible concept entities (entities). 
      IMPORTANT: ONLY extract entities that appear in the feature_description text. Return your answer as a JSON format string.

    Entity extraction rules (extract ALL possible entities FROM FEATURE_DESCRIPTION ONLY):
    1. extract EVERY possible entity, even if you're uncertain. It is CRITICAL to not miss any entities.
    2. IMPORTANT CLARIFICATION: Extract BOTH compound terms (e.g., 'tree-checker', 'inline backrefs') AND their individual components ONLY when the components have independent technical meaning in context. 
       - GOOD EXAMPLE: For 'AES-256 encryption', extract both the full term and 'AES', 'AES-256', 'encryption' as they all have technical meaning.
       - BAD EXAMPLE: For 'custom operations', DO NOT extract 'custom' alone as it has no specific technical meaning by itself.
    3. Focus on ALL NOUNS, NOUN PHRASES, TECHNICAL TERMS, ABBREVIATIONS, and DOMAIN-SPECIFIC CONCEPTS.
    4. For compound terms with underscores, hyphens, or camelCase, include both the full term AND each individual component as separate entities ONLY when the components have independent technical meaning in context.
       - GOOD EXAMPLE: For 'packet_fanout', extract both the full term and 'packet', 'fanout' as they all have technical meaning.
       - BAD EXAMPLE: For 'param_credit', DO NOT extract 'param' or 'credit' alone if they don't represent complete technical concepts in the Linux kernel context.
    5. Consider ALL technical jargon, system components, hardware elements, software concepts, and kernel-related terminology as potential entities.
    6. When you see numbers or identifiers that might represent versions, models, or specifications, include them as entities.
    7. DO NOT extract common verbs and generic action words like: 'add', 'support', 'implement', 'enable', 'check', 'export', 'create', 'improve', 'optimize', 'fix', 'allow', 'make', 'use', 'handle', 'provide'
    8. DO NOT extract generic descriptive words like: 'new', 'better', 'faster', 'improved', 'enhanced', 'basic', 'simple'
    You can refer to the examples field for guidance.",
    "examples": [{{
        "input": {{
            "h1": "Networking",
            "h2": "Protocols",
            "feature_description": "Fix packet_fanout implementation to properly handle protocol arrays in the queue"
        }},
        "output": {{
            "entities": ["packet_fanout", "packet", "fanout","protocol", "arrays", "protocol arrays", "queue"]
        }}
    }}, {{
        "input": {{
            "h1": "Processors",
            "h2": "Intel",
            "feature_description": "Add idle state support for Intel Comet Lake PCH"
        }},
        "output": {{
            "entities": ["idle state", "idle", "state", "Intel", "Comet Lake", "Intel Comet Lake", "PCH", "Intel Comet Lake PCH"]
        }}
    }}, {{
        "input": {{
            "h1": "File Systems",
            "h2": "Ext4",
            "feature_description": "Optimize inode allocation to improve performance on large directories"
        }},
        "output": {{
            "entities": ["inode allocation", "inode", "directories"]
        }}
    }}, {{
        "input": {{
            "h1": "Security",
            "h2": "Encryption",
            "feature_description": "Implement AES-256 encryption for secure data transmission"
        }},
        "output": {{
            "entities": ["AES-256 encryption","AES", "AES-256", "encryption", "secure data transmission", "data"]
        }}
    }}, {{
        "input": {{
            "h1": "Virtualization",
            "h2": "KVM",
            "feature_description": "Enhance virtual machine scheduling to reduce latency"
        }},
        "output": {{
            "entities": ["virtual machine scheduling", "virtual machine", "scheduling"]
        }}
    }}],
    "input": {{
        "h1": "{h1}",
        "h2": "{h2}",
        "feature_description": "{feature_description}"
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