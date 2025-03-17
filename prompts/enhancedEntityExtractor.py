# coding: utf-8
from langchain.prompts import PromptTemplate
import json
from typing import List, Dict, Any, Optional, Union
from .extractEntityWithContext import extractEntityWithContextPrompt

class EnhancedEntityExtractor:
    """
    增强型实体抽取器，支持多种抽取策略：
    1. 多模型并行抽取后合并结果
    2. 模型串行抽取（一个模型抽取后另一个模型补充）
    3. 单模型多次抽取后合并结果
    """
    
    # 补充提示模板 - 用于第二个模型补充抽取
    supplementary_template = """{{
    "instructions": "You are an expert in Named Entity Recognition (NER) tasks and also an expert in the Linux kernel.
      Given a Linux kernel feature description (feature_description), related contextual title information (h1, h2), 
      and a list of already extracted entities (existing_entities), your task is to: 
      identify and extract ADDITIONAL concept entities that were missed in the first extraction.
      IMPORTANT: ONLY extract entities that appear in the feature_description text and are NOT in the existing_entities list.
      Return your answer as a JSON format string.

    Entity extraction rules (extract ALL possible ADDITIONAL entities FROM FEATURE_DESCRIPTION ONLY):
    1. BE EXTREMELY THOROUGH - extract EVERY possible entity that was missed in the first extraction.
    2. Extract BOTH compound terms AND their components from feature_description that are not in existing_entities.
    3. Focus on ALL NOUNS, NOUN PHRASES, TECHNICAL TERMS, ABBREVIATIONS, and DOMAIN-SPECIFIC CONCEPTS.
    4. ALWAYS split compound terms with underscores, hyphens, or camelCase and include both the full term AND each individual component as separate entities.
    You can refer to the examples field for guidance.",
    "examples": [{{
        "input": {{
            "h1": "Networking",
            "h2": "Protocols",
            "feature_description": "Fix packet_fanout implementation to properly handle protocol arrays in the queue",
            "existing_entities": ["packet_fanout",  "protocol", "arrays", "queue"]
        }},
        "output": {{
            "reason": "I've extracted additional entities that were missed in the first extraction. I noticed that 'packet' and 'fanout' as individual components of 'packet_fanout' were missing. Also, 'protocol arrays' as a compound term were not in the existing list.",
            "additional_entities": ["packet", "fanout", "protocol arrays"]
        }}
    }}],
    "input": {{
        "h1": "{h1}",
        "h2": "{h2}",
        "feature_description": "{feature_description}",
        "existing_entities": {existing_entities}
    }}
}}
"""

    # 分段提示模板 - 用于单模型多次抽取
    segmented_template = """{{
    "instructions": "You are an expert in Named Entity Recognition (NER) tasks and also an expert in the Linux kernel.
      Given a Linux kernel feature description (feature_description) and related contextual title information (h1, h2), 
      your task is to: extract ABSOLUTELY ALL possible concept entities (entities) that match the SPECIFIC FOCUS AREAS listed below, 
      and describe why these entities are reasonable. 
      IMPORTANT: ONLY extract entities that appear in the feature_description text. Return your answer as a JSON format string.

    FOCUS AREAS FOR THIS EXTRACTION:
    {focus_areas}

    Entity extraction rules (extract ALL possible entities FROM FEATURE_DESCRIPTION ONLY that match the FOCUS AREAS):
    1. BE EXTREMELY THOROUGH - extract EVERY possible entity within the focus areas, even if you're uncertain.
    2. REMEMBER: It is better to extract too many entities than to miss important ones. When in doubt, ALWAYS include it.
    You can refer to the examples field for guidance.",
    "examples": [{{
        "input": {{
            "h1": "Networking",
            "h2": "Protocols",
            "feature_description": "Fix packet_fanout implementation to properly handle protocol arrays in the queue",
            "focus_areas": "1. Technical components and systems\n2. Hardware and software elements\n3. Networking-specific terminology"
        }},
        "output": {{
            "reason": "I've extracted all possible entities from the feature description that match the focus areas. For technical components, I extracted 'packet_fanout', 'protocol arrays', and 'queue'. For networking-specific terminology, I extracted 'packet', 'fanout', 'protocol', and 'arrays'.",
            "entities": ["packet_fanout", "packet", "fanout", "protocol", "arrays", "protocol arrays", "queue"]
        }}
    }}],
    "input": {{
        "h1": "{h1}",
        "h2": "{h2}",
        "feature_description": "{feature_description}",
        "focus_areas": "{focus_areas}"
    }}
}}
"""

    # 预定义的焦点区域组
    focus_area_groups = [
        "1. Extract BOTH compound terms AND their components from feature_description. For example, if 'memory management' appears, extract both 'memory management', 'memory', and 'management'. \n 2. Focus on ALL NOUNS, NOUN PHRASES, TECHNICAL TERMS, ABBREVIATIONS, and DOMAIN-SPECIFIC CONCEPTS that match the focus areas. \n 3. ALWAYS split compound terms with underscores, hyphens, or camelCase and include both the full term AND each individual component as separate entities.",   
        "1. For any technical term, also extract its variations that appear in the text (plural forms, abbreviated forms, etc.)\n2. When you see numbers or identifiers that might represent versions, models, or specifications, include them as entities.\n3. Avoid extracting standalone adjectives or adverbs unless they are part of a term (e.g., 'inline processing' is valid, but not 'inline' alone)",
        "1. DO NOT extract common verbs and generic action words like: 'add', 'support', 'implement', 'enable', 'check', 'export', 'create', 'improve', 'optimize', 'fix', 'allow', 'make', 'use', 'handle', 'provide'\n2. DO NOT extract generic descriptive words like: 'new', 'better', 'faster', 'improved', 'enhanced', 'basic', 'simple'\n3. Consider ALL technical jargon, system components, hardware elements, software concepts, and kernel-related terminology as potential entities."
    ]

    def __init__(self):
        self.prompt_template_supplementary = PromptTemplate(
            template=self.supplementary_template, 
            input_variables=["h1", "h2", "feature_description", "existing_entities"]
        )
        
        self.prompt_template_segmented = PromptTemplate(
            template=self.segmented_template, 
            input_variables=["h1", "h2", "feature_description", "focus_areas"]
        )
    
    def format_original_prompt(self, h1, h2, feature_description):
        """格式化原始提示"""
        return extractEntityWithContextPrompt(h1, h2, feature_description).format()
    
    def format_supplementary_prompt(self, h1, h2, feature_description, existing_entities):
        """格式化补充提示"""
        return self.prompt_template_supplementary.format(
            h1=h1,
            h2=h2,
            feature_description=feature_description,
            existing_entities=json.dumps(existing_entities)
        )
    
    def format_segmented_prompt(self, h1, h2, feature_description, focus_areas):
        """格式化分段提示"""
        return self.prompt_template_segmented.format(
            h1=h1,
            h2=h2,
            feature_description=feature_description,
            focus_areas=focus_areas
        )
    
    def merge_entities(self, entity_lists):
        """合并多个实体列表，去重"""
        merged = []
        for entity_list in entity_lists:
            for entity in entity_list:
                if entity not in merged:
                    merged.append(entity)
        return merged 