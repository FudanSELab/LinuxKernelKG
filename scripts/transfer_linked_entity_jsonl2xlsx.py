import json
import pandas as pd
import re

try:
    data = []
    file_path = 'output/entity_linking/linked_entities_gpt_mm_0414.jsonl'
    
    # 方法1: 逐行读取并组合成完整JSON
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        i = 0
        while i < len(lines):
            # 查找JSON对象开始
            while i < len(lines) and not lines[i].strip().startswith('{'):
                i += 1
            
            if i >= len(lines):
                break
                
            # 收集完整的JSON对象
            json_str = ""
            brace_count = 0
            while i < len(lines):
                line = lines[i].strip()
                json_str += line
                
                brace_count += line.count('{') - line.count('}')
                if brace_count == 0 and json_str.strip():
                    # 完整JSON对象
                    try:
                        obj = json.loads(json_str)
                        data.append(obj)
                    except json.JSONDecodeError as e:
                        print(f"JSON解析错误: {str(e)}, 内容: {json_str[:50]}...")
                    
                    json_str = ""
                    i += 1
                    break
                
                i += 1
    
    # 方法2: 如果方法1解析结果不理想，使用正则表达式查找JSON对象
    if len(data) < 800:
        print(f"方法1解析到{len(data)}个对象，尝试方法2...")
        data = []
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # 使用正则表达式找出所有可能的JSON对象
            pattern = r'(\{(?:[^{}]|(?R))*\})'
            matches = re.finditer(pattern, content, re.DOTALL)
            
            for match in matches:
                try:
                    json_str = match.group(0)
                    obj = json.loads(json_str)
                    data.append(obj)
                except json.JSONDecodeError:
                    continue
    
    # 方法3: 如果前两种方法都不理想，手动查找并解析
    if len(data) < 800:
        print(f"方法2解析到{len(data)}个对象，尝试方法3...")
        data = []
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
            start_idx = 0
            while True:
                # 找到下一个对象开始
                start_idx = content.find('{', start_idx)
                if start_idx == -1:
                    break
                
                # 手动跟踪括号匹配
                stack = ['{']
                end_idx = start_idx + 1
                
                while stack and end_idx < len(content):
                    if content[end_idx] == '{':
                        stack.append('{')
                    elif content[end_idx] == '}':
                        stack.pop()
                    end_idx += 1
                
                if not stack:  # 找到匹配的结束括号
                    try:
                        json_str = content[start_idx:end_idx]
                        obj = json.loads(json_str)
                        data.append(obj)
                    except json.JSONDecodeError:
                        pass
                
                start_idx = end_idx
    
    print(f"成功解析出{len(data)}个JSON对象")
    
    # 提取需要的字段
    processed_data = []
    for item in data:
        # 处理别名
        aliases = item.get('aliases', [])
        aliases_str = ", ".join(aliases) if isinstance(aliases, list) else str(aliases)
        
        # 处理外部链接
        urls = []
        external_links = item.get('external_links', [])
        if isinstance(external_links, list):
            for link in external_links:
                if isinstance(link, dict):
                    if 'url' in link and isinstance(link['url'], str):
                        urls.append(link['url'])
                    elif 'url' in link and isinstance(link['url'], list):
                        urls.extend(link['url'])
        url_str = ", ".join(urls)
        
        processed_data.append({
            'name': item.get('name', ''),
            'feature_id': item.get('feature_id', ''),
            'context': item.get('context', ''),
            'aliases': aliases_str,
            'url': url_str
        })

    # 创建DataFrame并保存为xlsx
    df = pd.DataFrame(processed_data)
    
    # 统计根据name去重后的元素数量
    unique_names_count = df['name'].nunique()
    unique_names_df = df.drop_duplicates(subset=['name'])
    
    print(f"原始数据有 {len(df)} 条记录")
    print(f"根据name去重后有 {unique_names_count} 条记录")
    
    output_path = 'output/entity_linking/linked_entities_processed_gpt_mm_0414.xlsx'
    df.to_excel(output_path, index=False)

    print(f"已处理 {len(processed_data)} 条记录并保存到 {output_path}")
    
except Exception as e:
    print(f"处理过程中出现错误: {str(e)}")