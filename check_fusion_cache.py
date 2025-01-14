import json

def clean_empty_code_references(input_file, output_file=None):
    # 如果没有指定输出文件，则覆盖输入文件
    if output_file is None:
        output_file = input_file
    
    # 读取JSON文件
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 遍历所有实体
    for entity_key, entity_data in data.items():
        if "references" in entity_data:
            # 过滤掉空的code引用
            entity_data["references"] = [
                ref for ref in entity_data["references"]
                if not (ref["reference_type"] == "code" and not ref["references"])
            ]
    
    # 写入更新后的JSON文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# 使用示例
input_file = "data/cache/fusion_cache.json"
clean_empty_code_references(input_file)
