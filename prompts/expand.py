# coding: utf-8
from langchain.prompts import PromptTemplate
import json

class expandPrompt:

    template = """{{
    "instructions": "你是一个 linux 内核的专家。给你一个 linux 内核特性的描述以及其对应的若干 commit 的标题和提交信息，你的任务是为这个特性写一个多方面的扩写版描述。你的扩写需包含以下几个方面：1. 该特性涉及到的一些 linux 内核中的专有名词及其解释 (proper_nouns)；2. 为了让开发者理解该特性，需要哪些具体的，与这个特性直接相关的背景知识 (background_knowledge)；3. 该特性被实现前后，linux 内核发生了怎样的变化 (kernel_changes)；4. 你对该特性的综合理解 (comprehensive_understanding)。用英语回答。用json格式字符串返回你的回答。你可以参考 examples 字段给出的例子。",
    "examples": [
        "input": {{
            "feature_description": "Prohibit the last subpage from reusing the entire large folio",
            "commits": [{{"commit_subject": "mm: prohibit the last subpage from reusing the entire large folio", "commit_message": "In a Copy-on-Write (CoW) scenario, the last subpage will reuse the entire\nlarge folio, resulting in the waste of (nr_pages - 1) pages.  This wasted\nmemory remains allocated until it is either unmapped or memory reclamation\noccurs.\n\nThe following small program can serve as evidence of this behavior\n\n main()\n {{\n #define SIZE 1024 * 1024 * 1024UL\n         void *p = malloc(SIZE);\n         memset(p, 0x11, SIZE);\n         if (fork() == 0)\n                 _exit(0);\n         memset(p, 0x12, SIZE);\n         printf("done\\n");\n         while(1);\n }}\n\nFor example, using a 1024KiB mTHP by:\n echo always > /sys/kernel/mm/transparent_hugepage/hugepages-1024kB/enabled\n\n(1) w/o the patch, it takes 2GiB,\n\nBefore running the test program,\n / # free -m\n                total        used        free      shared  buff/cache   available\n Mem:            5754          84        5692           0          17        5669\n Swap:              0           0           0\n\n / # /a.out &\n / # done\n\nAfter running the test program,\n / # free -m\n                 total        used        free      shared  buff/cache   available\n Mem:            5754        2149        3627           0          19        3605\n Swap:              0           0           0\n\n(2) w/ the patch, it takes 1GiB only,\n\nBefore running the test program,\n / # free -m\n                 total        used        free      shared  buff/cache   available\n Mem:            5754          89        5687           0          17        5664\n Swap:              0           0           0\n\n / # /a.out &\n / # done\n\nAfter running the test program,\n / # free -m\n                total        used        free      shared  buff/cache   available\n Mem:            5754        1122        4655           0          17        4632\n Swap:              0           0           0\n\nThis patch migrates the last subpage to a small folio and immediately\nreturns the large folio to the system. It benefits both memory availability\nand anti-fragmentation.\n\nLink: https://lkml.kernel.org/r/20240308092721.144735-1-21cnbao@gmail.com\nSigned-off-by: Barry Song <v-songbaohua@oppo.com>\nAcked-by: David Hildenbrand <david@redhat.com>\nCc: Ryan Roberts <ryan.roberts@arm.com>\nCc: Lance Yang <ioworker0@gmail.com>\nSigned-off-by: Andrew Morton <akpm@linux-foundation.org>\n\n"}}]
        }},
        "output": {{
            "proper_nouns": [
                {{"Copy-on-Write (CoW)": Copy-on-Write (COW) is a memory management technique used in the Linux kernel to optimize the process of creating new processes or modifying shared resources. The core idea behind COW is to defer the actual copying of data until it is necessary, thereby reducing the overhead associated with creating new processes or modifying shared data.}},
                {{"mTHP": mTHP, which stands for "Memory Transparent Huge Pages," is a feature in the Linux kernel designed to improve memory performance by using larger memory pages, known as huge pages. Traditional memory pages in Linux are typically 4KB in size, but huge pages can be much larger, such as 2MB or even 1GB, depending on the architecture.}},
                {{"folio": In the Linux kernel, a "folio" is a higher-level abstraction introduced to manage memory pages more efficiently, especially in the context of file system operations. The concept of a folio aims to address some of the inefficiencies associated with traditional page management, particularly when dealing with large files or when performing operations that span multiple pages.}},
            ],
            "background_knowledge": [
                "In a Copy-on-Write (CoW) scenario, the last subpage will reuse the entire large folio, resulting in the waste of (nr_pages - 1) pages. This wasted memory remains allocated until it is either unmapped or memory reclamation occurs."
            ],
            "kernel_changes": [
                "Before the implementation of this feature, the Linux kernel allowed the last subpage to reuse the entire large folio in a Copy-on-Write (CoW) scenario, leading to the waste of (nr_pages - 1) pages. This wasted memory remained allocated until it was either unmapped or memory reclamation occurred. After the implementation, the kernel was modified to migrate the last subpage to a small folio and immediately return the large folio to the system. This change reduced memory waste, improved memory availability, and reduced fragmentation. As a result, memory usage in CoW scenarios was optimized, leading to better system performance and resource utilization."
            ],
            "comprehensive_understanding": "This feature optimizes memory management in Copy-on-Write (CoW) scenarios by preventing the last subpage from reusing the entire large folio. Instead, it migrates the last subpage to a small folio and immediately returns the large folio to the system. This reduces memory waste, improves memory availability, and mitigates fragmentation, ultimately enhancing system performance and resource utilization."
        }}
    ],
    "input": {{
        "feature_description": "{feature_description}",
        "commits": {commits}
    }}
}}
"""

    prompt_template_expand = PromptTemplate(template=template, input_variables=["feature_description", "commits"])

    def __init__(self, feature_description, commits):
        self.feature_description = feature_description
        self.commits = commits

    def format(self):
        return self.prompt_template_expand.format(
            feature_description = self.feature_description,
            commits = json.dumps(self.commits, ensure_ascii=False, indent=None)
        )


# 测试代码

# test_obj = [
#     {
#         "commit_subject": "test1",
#         "commit_message": "test1"
#     },
#     {
#         "commit_subject": "test2",
#         "commit_message": "test2"
#     }
# ]

# print(expandPrompt(feature_description="test", commits=test_obj).format())