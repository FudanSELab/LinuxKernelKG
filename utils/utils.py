# 去除 llm response 的开头 ```json 和末尾 ``` 两行
def strip_json(json_str):
    return json_str.lstrip('```json').rstrip('```')
