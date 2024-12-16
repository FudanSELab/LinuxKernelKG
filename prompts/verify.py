# coding: utf-8
from langchain.prompts import PromptTemplate
import json

class verifyPrompt:

    template = """{{
    "instructions": "你是一个知识图谱专家，同时也是 linux 内核的专家。给你一个 linux 内核特性的描述 (feature_description)、对应的若干 commit 的标题和提交信息 (commits)，以及从中抽取出的实体 (entities) 和关系三元组 (triples)。你的任务是：验证这些实体和关系三元组是否合理，只保留合理的结果。合理的实体和关系三元组需要满足：1. 在 linux 内核中存在；2. 不是只在给出的提交中出现，而是在整个 linux 内核中存在的实体和成立的关系；3. 实体必须是能够独立存在的概念名词，关系(e1, r, e2)中e1必须是实体，e2可以是实体或者是属性。用英语回答。用json格式字符串返回你的回答。你可以参考 examples 字段给出的例子。",
    "examples": [{{
        "input": {{
            "feature_description": "Prohibit the last subpage from reusing the entire large folio",
            "commits": [{{"commit_subject": "mm: prohibit the last subpage from reusing the entire large folio", "commit_message": "In a Copy-on-Write (CoW) scenario, the last subpage will reuse the entire\nlarge folio, resulting in the waste of (nr_pages - 1) pages.  This wasted\nmemory remains allocated until it is either unmapped or memory reclamation\noccurs.\n\nThe following small program can serve as evidence of this behavior\n\n main()\n {{\n #define SIZE 1024 * 1024 * 1024UL\n         void *p = malloc(SIZE);\n         memset(p, 0x11, SIZE);\n         if (fork() == 0)\n                 _exit(0);\n         memset(p, 0x12, SIZE);\n         printf("done\\n");\n         while(1);\n }}\n\nFor example, using a 1024KiB mTHP by:\n echo always > /sys/kernel/mm/transparent_hugepage/hugepages-1024kB/enabled\n\n(1) w/o the patch, it takes 2GiB,\n\nBefore running the test program,\n / # free -m\n                total        used        free      shared  buff/cache   available\n Mem:            5754          84        5692           0          17        5669\n Swap:              0           0           0\n\n / # /a.out &\n / # done\n\nAfter running the test program,\n / # free -m\n                 total        used        free      shared  buff/cache   available\n Mem:            5754        2149        3627           0          19        3605\n Swap:              0           0           0\n\n(2) w/ the patch, it takes 1GiB only,\n\nBefore running the test program,\n / # free -m\n                 total        used        free      shared  buff/cache   available\n Mem:            5754          89        5687           0          17        5664\n Swap:              0           0           0\n\n / # /a.out &\n / # done\n\nAfter running the test program,\n / # free -m\n                total        used        free      shared  buff/cache   available\n Mem:            5754        1122        4655           0          17        4632\n Swap:              0           0           0\n\nThis patch migrates the last subpage to a small folio and immediately\nreturns the large folio to the system. It benefits both memory availability\nand anti-fragmentation.\n\nLink: https://lkml.kernel.org/r/20240308092721.144735-1-21cnbao@gmail.com\nSigned-off-by: Barry Song <v-songbaohua@oppo.com>\nAcked-by: David Hildenbrand <david@redhat.com>\nCc: Ryan Roberts <ryan.roberts@arm.com>\nCc: Lance Yang <ioworker0@gmail.com>\nSigned-off-by: Andrew Morton <akpm@linux-foundation.org>\n\n"}}],
            "entities": ["Copy-on-Write (CoW)", "mTHP", "folio", "memory reclamation", "memory availability", "anti-fragmentation", "invalid_entity"],
            "triples": [["large folio reuse", "influences", "memory waste"], ["memory waste", "dependsOn", "memory reclaim"], ["last subpage", "causes", "large folio reuse"], ["invalid_entity1", "causes", "invalid_entity2"], ["This wasted memory", "remains allocated", "until it is either unmapped or memory reclamation occurs"]]
        }},
        "output": {{
            "entities": ["Copy-on-Write (CoW)", "folio", "memory reclamation", "memory availability", "anti-fragmentation"],
            "triples": [["large folio reuse", "influences", "memory waste"], ["memory waste", "dependsOn", "memory reclaim"], ["last subpage", "causes", "large folio reuse"]],
        }}
    }}],
    "input": {{
        "feature_description": "{feature_description}",
        "commits": {commits},
        "entities": {entities},
        "triples": {triples}
    }}
}}
"""

    prompt_template_verify = PromptTemplate(
        template=template,
        input_variables=["feature_description", "commits", "entities", "triples"]
    )

    def __init__(self, feature_description, commits, entities, triples):
        self.feature_description = feature_description
        self.commits = commits
        self.entities = entities
        self.triples = triples

    def format(self):
        return self.prompt_template_verify.format(
            feature_description = self.feature_description,
            commits = json.dumps(self.commits, ensure_ascii=False, indent=None),
            entities = json.dumps(self.entities, ensure_ascii=False, indent=None),
            triples = json.dumps(self.triples, ensure_ascii=False, indent=None)
        )


# 测试代码

# test_obj = {
#     'feature_description': 'test',
#     'commits': [{'commit_subject': 'test1', 'commit_message': 'test1'}, {'commit_subject': 'test2', 'commit_message': 'test2'}],
#     'entities': ['test_entity1', 'test_entity2'],
#     'triples': [['test_entity1', 'causes', 'test_entity2']]
# }

# print(verifyPrompt(**test_obj).format())
