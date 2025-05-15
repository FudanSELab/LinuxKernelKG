import json
import pandas as pd
import os

def compare_names(json_file='input.json', xlsx_file='input.xlsx', output_file='missing_names.txt'):
    print(f"比较文件中...\n源JSON文件: {json_file}\nExcel文件: {xlsx_file}\n输出文件: {output_file}")
    
    # 检查输入文件是否存在
    if not os.path.exists(json_file):
        print(f"错误: 找不到JSON文件 '{json_file}'")
        return
    
    if not os.path.exists(xlsx_file):
        print(f"错误: 找不到Excel文件 '{xlsx_file}'")
        return
    
    # 读取JSONL文件
    try:
        json_names = []
        with open(json_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():  # 跳过空行
                    item = json.loads(line)
                    if 'name' in item:
                        json_names.append(item['name'])
        print(f"从JSONL文件中提取了 {len(json_names)} 个名称")
    except Exception as e:
        print(f"读取JSONL文件时出错: {e}")
        return
    
    # 读取Excel文件
    try:
        df = pd.read_excel(xlsx_file)
        if 'name' not in df.columns:
            print("Excel文件中缺少'name'列")
            return
    except Exception as e:
        print(f"读取Excel文件时出错: {e}")
        return
    
    # 获取所有aliases，处理空值
    all_aliases = []
    
    # 检查是否存在aliases列
    has_aliases_column = 'aliases' in df.columns
    
    for idx, row in df.iterrows():
        if has_aliases_column and pd.notna(row.get('aliases')) and row['aliases'].strip():
            # 如果有aliases列且不为空，使用aliases
            aliases_str = row['aliases']
            if isinstance(aliases_str, str):
                for alias in aliases_str.split(','):
                    all_aliases.append(alias.strip())
        else:
            # 如果aliases为空或不存在，使用name字段
            if pd.notna(row['name']):
                all_aliases.append(row['name'].strip())
    
    print(f"从Excel文件中提取了 {len(all_aliases)} 个别名")
    
    # 查找缺失的名称
    missing_names = [name for name in json_names if name not in all_aliases]
    
    # 将结果写入输出文件
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for name in missing_names:
                f.write(f"{name}\n")
        print(f"比较完成。找到 {len(missing_names)} 个缺失的名称，已保存到 {output_file}")
    except Exception as e:
        print(f"写入输出文件时出错: {e}")

# 你可以在此直接修改文件路径
json_file_path = 'output/entity_linking/pre_linked_entities_20250416.jsonl'    # 默认JSONL文件路径
xlsx_file_path = 'output/entity_linking/linked_entities_processed_gpt_mm_0414.xlsx'    # 默认Excel文件路径
output_file_path = 'output/entity_linking/missing_names_gpt_mm_0416.txt'  # 默认输出文件路径

# 运行比较函数
if __name__ == "__main__":
    compare_names(json_file_path, xlsx_file_path, output_file_path)