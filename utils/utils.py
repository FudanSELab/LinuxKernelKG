import json

def strip_json(text):
    """
    从文本中提取JSON字符串
    Args:
        text: 文本内容，可以是被```json和```包围的格式，也可以是直接的JSON字符串
    Returns:
        清理后的JSON字符串
    """
    # 尝试查找```json和```标记
    start_marker = "```json"
    end_marker = "```"
    
    start = text.find(start_marker)
    
    # 如果找到了标记，按原逻辑处理
    if start != -1:
        # 移动到标记后的实际JSON开始位置
        start = start + len(start_marker)
        
        # 从start位置开始查找结束标记
        end = text.find(end_marker, start)
        if end == -1:
            raise ValueError("No closing ``` marker found in the text")
            
        # 提取JSON部分
        json_str = text[start:end].strip()
    else:
        # 如果没有标记，直接使用整个文本
        json_str = text.strip()
    
    try:
        # 验证是否为有效的JSON
        json.loads(json_str)
        return json_str
    except json.JSONDecodeError:
        # 如果解析失败，尝试进行清理
        lines = json_str.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('//') and not line.startswith('/*'):
                cleaned_lines.append(line)
        cleaned_json = ' '.join(cleaned_lines)
        return cleaned_json