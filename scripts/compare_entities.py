#!/usr/bin/env python3
import json
import re

def clean_entity(entity):
    # 删除括号及其内容
    entity = re.sub(r'\([^)]*\)', '', entity)
    # 去除首尾空格
    entity = entity.strip()
    return entity

def read_txt_entities(file_path):
    entities = set()
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            # 跳过标题行
            if line.startswith('实体'):
                continue
            # 获取逗号前的实体部分
            entity = line.split(',')[0]
            entity = clean_entity(entity)
            if entity:
                entities.add(entity)
    return entities

def read_json_entities(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # 清理每个实体中的括号
        entities = {clean_entity(entity) for entity in data}
    return entities

def main():
    # 读取两个文件中的实体
    txt_entities = read_txt_entities('scripts/entity_frequency.txt')
    json_entities = read_json_entities('data/merged.json')
    
    # 找出重合的实体
    common_entities = txt_entities.intersection(json_entities)
    
    # 输出结果
    print(f"TXT文件中的实体数量: {len(txt_entities)}")
    print(f"JSON文件中的实体数量: {len(json_entities)}")
    print(f"重合的实体数量: {len(common_entities)}")
    print("\n重合的实体列表:")
    for entity in sorted(common_entities):
        print(entity)

if __name__ == "__main__":
    main() 