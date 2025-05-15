import json
import os
import sys
from collections import Counter

def count_filtered_entities(file_paths):
    # 存储所有 filtered_entities
    all_entities = []
    
    # 处理的文件数量和条目数量
    processed_files = 0
    processed_records = 0
    
    # 处理每个文件
    for file_path in file_paths:
        if not os.path.exists(file_path):
            print(f"错误: 文件 '{file_path}' 不存在")
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                # 逐行读取文件，假设每行是一个 JSON 对象
                for line_num, line in enumerate(file, 1):
                    try:
                        # 解析 JSON 数据
                        line = line.strip()
                        if not line:  # 跳过空行
                            continue
                            
                        data = json.loads(line)
                        processed_records += 1
                        
                        # 获取 filtered_entities 列表
                        entities = data.get('extraction_result', {}).get('filtered_entities', [])
                        
                        # 将实体添加到总列表中
                        all_entities.extend(entities)
                    except json.JSONDecodeError:
                        print(f"警告: 在文件 '{file_path}' 的第 {line_num} 行无法解析 JSON: {line[:50]}...")
                    except Exception as e:
                        print(f"在文件 '{file_path}' 的第 {line_num} 行处理数据时出错: {e}")
            
            processed_files += 1
            print(f"处理完成: '{file_path}'")
            
        except Exception as e:
            print(f"读取文件 '{file_path}' 时出错: {e}")
    
    # 统计结果
    total_count = len(all_entities)  # 不去重的总数
    unique_entities = set(all_entities)  # 去重后的实体
    unique_count = len(unique_entities)  # 去重后的数量
    
    # 统计每个实体出现的次数
    entity_counter = Counter(all_entities)
    
    return {
        "processed_files": processed_files,
        "processed_records": processed_records,
        "total_count": total_count,
        "unique_count": unique_count,
        "entity_counter": entity_counter
    }

def print_results(stats):
    print("\n===== 汇总统计结果 =====")
    print(f"处理文件数: {stats['processed_files']}")
    print(f"处理数据条目: {stats['processed_records']}")
    print(f"总共有 {stats['total_count']} 个 filtered_entities (不去重)")
    print(f"总共有 {stats['unique_count']} 个唯一的 filtered_entities (去重)")
    
    # 打印出现频率最高的前20个实体
    print("\n出现频率最高的 20 个实体:")
    for entity, count in stats["entity_counter"].most_common(20):
        print(f"  {entity}: {count} 次")
        
    # 将所有实体按频率导出到文件
    with open("entity_frequency.txt", "w", encoding="utf-8") as f:
        f.write("实体,出现次数\n")
        for entity, count in stats["entity_counter"].most_common():
            f.write(f"{entity},{count}\n")
    
    print("\n所有实体频率已导出到 'entity_frequency.txt'")

def main():
    # 从命令行参数获取文件路径
    if len(sys.argv) < 2:
        print("用法: python count_entities.py file1.json [file2.json ...]")
        return
    
    file_paths = sys.argv[1:]
    print(f"开始处理 {len(file_paths)} 个文件...")
    stats = count_filtered_entities(file_paths)
    print_results(stats)

if __name__ == "__main__":
    main()
