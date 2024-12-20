import json

def extract_wikipedia_links(input_file, output_file):
    # 读取 JSON 文件
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 提取 linking 部分
    linking_data = data.get("linking", [])
    
    # 准备输出数据
    extracted_data = []
    for item in linking_data:
        mention = item.get("mention", "")
        linked_entity = item.get("linked_entity", "")
        wikipedia_url = item.get("wikipedia_url", "")
        
        # 只提取 mention 或 linked_entity 和 wikipedia_url
        if wikipedia_url:
            extracted_data.append({
                "concept": mention or linked_entity,
                "wikipedia_url": wikipedia_url
            })
    
    # 将提取的数据写入新的 JSON 文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(extracted_data, f, ensure_ascii=False, indent=4)

# 使用示例
extract_wikipedia_links('../output/kg_results_with_wiki_urls.json', '../output/extracted_wikipedia_links.json')
