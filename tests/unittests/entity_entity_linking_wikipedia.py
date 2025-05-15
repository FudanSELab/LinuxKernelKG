import json
import os
import glob
import pdb

def analyze_entities(file_paths):
    total_entities = 0
    entity_names = set()
    
    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entity = json.loads(line)
                        total_entities += 1
                        # pdb.set_trace()
                        # 字符串entity要是http开头才算
                        if not isinstance(entity, str) or not entity.startswith('http'):
                            continue
                        print(entity)   
                        entity_names.add(entity)
                        # if 'name' in entity:
                        #     entity_names.add(entity['name'])
                    except json.JSONDecodeError:
                        continue
            
            print(f"文件 {os.path.basename(file_path)} 处理完成")
        except Exception as e:
            print(f"处理文件 {file_path} 时出错: {str(e)}")
    
    return {
        'total_entities': total_entities,
        'unique_name_entities': len(entity_names)
    }

# 可以处理多个文件
def main():
    # 可以指定多个文件，或使用通配符
    # file_paths = glob.glob('output/entity_linking/*.jsonl')
    # 也可以手动指定文件列表
    file_paths = ['output/entity_linking/linked_entities_openai_0409.jsonl','output/entity_linking/linked_entities_20250409_1533.jsonl']
    
    if not file_paths:
        print("未找到匹配的文件")
        return
    
    print(f"将处理以下文件: {', '.join(os.path.basename(f) for f in file_paths)}")
    result = analyze_entities(file_paths)
    print(f"总实体数量: {result.get('total_entities', 0)}")
    print(f"按名称去重后的实体数量: {result.get('unique_name_entities', 0)}")

if __name__ == "__main__":
    main()
