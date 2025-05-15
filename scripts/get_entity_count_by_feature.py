import json
import argparse
from collections import defaultdict

def count_entities_by_feature_id(input_files, file_id_ranges=None):
    """
    统计指定feature_id范围内的实体数量
    
    参数:
        input_files: jsonl文件路径列表
        file_id_ranges: 字典，键为文件路径，值为(start_id, end_id)元组
    
    返回:
        每个feature_id的实体数量和总实体集合
    """
    # 初始化结果
    id_entities = {}  # 存储每个feature_id对应的实体列表
    all_entities = set()  # 存储所有不重复的实体
    
    # 处理每个输入文件
    for input_file in input_files:
        # 获取当前文件的ID范围
        start_id, end_id = None, None
        if file_id_ranges and input_file in file_id_ranges:
            start_id, end_id = file_id_ranges[input_file]
        
        # 读取文件并统计
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                    
                try:
                    data = json.loads(line)
                    feature_id = data.get('feature_id') or data.get('feature', {}).get('feature_id')
                    
                    if feature_id is None:
                        continue
                    
                    # 如果有特定ID范围，则过滤
                    if start_id is not None and end_id is not None:
                        if not (start_id <= feature_id <= end_id):
                            continue
                        
                    # 提取实体
                    entities = data.get('extraction_result', {}).get('filtered_entities', [])
                    
                    # 记录该feature_id的实体
                    if feature_id in id_entities:
                        id_entities[feature_id].extend(entities)
                    else:
                        id_entities[feature_id] = entities
                    
                    # 记录所有不重复实体
                    all_entities.update(entities)
                    
                except json.JSONDecodeError:
                    print(f"Warning: Invalid JSON line in {input_file}: {line}")
                    continue
    
    return id_entities, all_entities

def main():
    parser = argparse.ArgumentParser(description='统计指定feature_id范围内的实体数量')
    parser.add_argument('input_files', nargs='+', help='输入的jsonl文件路径，可以指定多个文件')
    parser.add_argument('--id_ranges', nargs='+', help='每个文件的ID范围，格式: 文件路径:开始ID-结束ID')
    parser.add_argument('--default_start_id', type=int, default=30161, help='默认起始feature_id')
    parser.add_argument('--default_end_id', type=int, default=30357, help='默认结束feature_id')
    args = parser.parse_args()
    
    # 解析文件ID范围
    file_id_ranges = {}
    if args.id_ranges:
        for range_str in args.id_ranges:
            try:
                file_path, id_range = range_str.split(':')
                start_id, end_id = map(int, id_range.split('-'))
                file_id_ranges[file_path] = (start_id, end_id)
            except ValueError:
                print(f"Warning: 无效的ID范围格式: {range_str}，应为 '文件路径:开始ID-结束ID'")
    
    # 为没有指定范围的文件设置默认范围
    for file_path in args.input_files:
        if file_path not in file_id_ranges:
            file_id_ranges[file_path] = (args.default_start_id, args.default_end_id)
    
    print(f"正在处理 {len(args.input_files)} 个文件...")
    for file_path in args.input_files:
        start_id, end_id = file_id_ranges[file_path]
        print(f"文件 {file_path} 使用ID范围: {start_id}-{end_id}")
    
    id_entities, all_entities = count_entities_by_feature_id(args.input_files, file_id_ranges)
    
    # 输出结果
    print(f"\n{'Feature ID':^10} | {'实体数量':^10}")
    print("-" * 23)
    
    # 按ID排序
    total_entities = 0
    for feature_id in sorted(id_entities.keys()):
        entity_count = len(id_entities[feature_id])
        total_entities += entity_count
        print(f"{feature_id:^10} | {entity_count:^10}")
    
    print("\n总计:")
    print(f"Feature ID数量: {len(id_entities)}")
    print(f"实体总数(含重复): {total_entities}")
    print(f"不重复实体总数: {len(all_entities)}")
    print(f"实体集合: {all_entities}")

if __name__ == "__main__":
    main()