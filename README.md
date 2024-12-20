# LinuxKernelKG

运行时需要把项目目录添加到环境变量`PYTHONPATH`。例如 windows cmd 下：`set PYTHONPATH=%CD%;%PYTHONPATH%`

#### 1. entity_links.xlsx
数据集的Excel文件包含以下列：

| 列名 | 类型 | 说明 | 示例 |
|------|------|------|------|
| mention_id | 整数 | 实体的唯一标识符 | 1 |
| original_mention | 字符串 | 原始实体名称 | "北京大学" |
| overall_linkable | 布尔值 | 是否存在整体链接 | True 或 False |
| ngram_linkable | 布尔值 | 是否存在N-gram链接 | True 或 False |
| overall_wikipedia_link | 字符串 | 整体维基百科链接 | "https://zh.wikipedia.org/wiki/北京大学" |
| ngram_wikipedia_link | 字符串 | N-gram维基百科链接列表 | "[{'ngram_mention': '北京大学', 'wikipedia_link': 'https://...'}]" |
