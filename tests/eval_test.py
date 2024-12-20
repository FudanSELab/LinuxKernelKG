import json
from pathlib import Path

def process_kg_results(input_file, output_file):
    # 读取输入文件
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 筛选有wikipedia链接的条目并去重
    seen_urls = set()
    unique_entries = []
    for entry in data.get("linking", []):
        wiki_url = entry.get("wikipedia_url")
        if wiki_url is not None and wiki_url not in seen_urls:
            seen_urls.add(wiki_url)
            unique_entries.append(entry)
    
    wiki_entries = {
        "fusion": data.get("fusion", []),
        "linking": unique_entries
    }
    
    # 统计信息
    total_entries = len(data.get("linking", []))
    total_wiki_entries = len([entry for entry in data.get("linking", []) 
                            if entry.get("wikipedia_url") is not None])
    unique_wiki_entries = len(unique_entries)
    duplicate_count = total_wiki_entries - unique_wiki_entries
    
    # 写入输出文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(wiki_entries, f, indent=2, ensure_ascii=False)
    
    # 返回统计信息
    return {
        "total_entries": total_entries,
        "wiki_entries": total_wiki_entries,
        "unique_entries": unique_wiki_entries,
        "duplicate_count": duplicate_count,
        "percentage": round(unique_wiki_entries / total_entries * 100, 2) if total_entries > 0 else 0
    }

def main():
    # 设置输入输出文件路径
    input_file = "../output/kg_results_20241219_223522_final.json"
    output_file = "../output/kg_results_with_wiki_urls.json"
    
    # 确保输出目录存在
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    
    # 处理文件
    stats = process_kg_results(input_file, output_file)
    
    # 打印统计信息
    print(f"处理完成！")
    print(f"总条目数: {stats['total_entries']}")
    print(f"包含维基百科链接的条目数: {stats['wiki_entries']}")
    print(f"去重后的条目数: {stats['unique_entries']}")
    print(f"重复条目数: {stats['duplicate_count']}")
    print(f"去重后占总条目比例: {stats['percentage']}%")
    print(f"结果已保存至: {output_file}")

if __name__ == "__main__":
    main()
