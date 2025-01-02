# coding: utf-8
from langchain.prompts import PromptTemplate
import json

class extractTriplePrompt:

    template = """{{
    "instructions": "你是一个关系抽取 (Relation Extraction) 任务的专家，同时也是 linux 内核的专家。给你一个 linux 内核特性的描述 (feature_description)、对应的若干 commit 的标题和提交信息 (commits)。你的任务是：根据这些信息提取出在 linux 内核中涉及到的与这个 feature 相关关系三元组 (triples)，形如(entity1, relation, entity2)。关系的类型参考 relations 字段的定义。用英语回答。用json格式字符串返回你的回答。你可以参考 examples 字段给出的例子。",
    "relations": [
        {{
            "name": "synonym",
            "description": "A synonym relation means that entity1 has the same or nearly the same meaning as entity2 in linux kernel.",
            "example": "(kthread, synonym, kernel thread)"
        }},
        {{
            "name": "isA",
            "description": "An isA relation means that a hypernym entity2 that is more generic or abstract than entity1 and encompasses a broader category.",
            "example": "(internal fragment, isA, fragment)"
        }},
        {{
            "name": "partOf",
            "description": "An isPartOf relation means that entity1 is a component or constituent of entity2 that is larger. This relation shows that an item is a part of a bigger whole.",
            "example": "(slab manager, partOf, memory management)"
        }},
        {{
            "name": "contains",
            "description": "A contains relation means that entity1 includes or holds entity2, something else within it. This indicates that one item has the other as a subset or component.",
            "example": "(physical memory, contains, page)"
        }},
        {{
            "name": "causes",
            "description": "A causes relation means that one event or action entity1 brings about another entity2. This indicates a causal relation where one thing directly results in the occurrence of another.",
            "example": "(page fault, causes, memory allocation)"
        }},
        {{
            "name": "dependsOn",
            "description": "A dependsOn relation means that entity1 relies on entity2 to function properly in linux kernel. This indicates a strong dependency where entity1 cannot work correctly without entity2.",
            "example": "(page reclaim, dependsOn, memory pressure)"
        }},
        {{
            "name": "influences",
            "description": "An influences relation means that entity1 affects or changes the behavior of entity2 in linux kernel. This shows how one component can impact another's operation or performance.",
            "example": "(memory pressure, influences, page allocation)"
        }}
    ]
    "examples": [{{
        "input": {{
            "feature_description": "Prohibit the last subpage from reusing the entire large folio",
            "commits": "commit_subject:\nmm: prohibit the last subpage from reusing the entire large folio\ncommit_message:\nIn a Copy-on-Write (CoW) scenario, the last subpage will reuse the entire\nlarge folio, resulting in the waste of (nr_pages - 1) pages.  This wasted\nmemory remains allocated until it is either unmapped or memory reclamation\noccurs.\n\nThe following small program can serve as evidence of this behavior\n\n main()\n {{\n #define SIZE 1024 * 1024 * 1024UL\n         void *p = malloc(SIZE);\n         memset(p, 0x11, SIZE);\n         if (fork() == 0)\n                 _exit(0);\n         memset(p, 0x12, SIZE);\n         printf("done\\n");\n         while(1);\n }}\n\nFor example, using a 1024KiB mTHP by:\n echo always > /sys/kernel/mm/transparent_hugepage/hugepages-1024kB/enabled\n\n(1) w/o the patch, it takes 2GiB,\n\nBefore running the test program,\n / # free -m\n                total        used        free      shared  buff/cache   available\n Mem:            5754          84        5692           0          17        5669\n Swap:              0           0           0\n\n / # /a.out &\n / # done\n\nAfter running the test program,\n / # free -m\n                 total        used        free      shared  buff/cache   available\n Mem:            5754        2149        3627           0          19        3605\n Swap:              0           0           0\n\n(2) w/ the patch, it takes 1GiB only,\n\nBefore running the test program,\n / # free -m\n                 total        used        free      shared  buff/cache   available\n Mem:            5754          89        5687           0          17        5664\n Swap:              0           0           0\n\n / # /a.out &\n / # done\n\nAfter running the test program,\n / # free -m\n                total        used        free      shared  buff/cache   available\n Mem:            5754        1122        4655           0          17        4632\n Swap:              0           0           0\n\nThis patch migrates the last subpage to a small folio and immediately\nreturns the large folio to the system. It benefits both memory availability\nand anti-fragmentation.\n\n"
        }},
        "output": {{
            "triples": [["large folio reuse", "influences", "memory waste"], ["memory waste", "dependsOn", "memory reclaim"], ["last subpage", "causes", "large folio reuse"]]
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

# print(extractTriplePrompt(**test_obj).format())