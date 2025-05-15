import json
import sys

def process_fusion_cache(file_path):
    """
    处理 fusion cache JSON 文件，统计元素总数及URL有内容的元素。

    Args:
        file_path (str): JSON文件的路径。
    """
    total_elements = 0
    elements_with_content_url = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, dict):
            print(f"错误：文件 {file_path} 的顶层结构不是一个字典。", file=sys.stderr)
            return

        total_elements = len(data)

        for element_key, element_value_list in data.items():
            has_content = False
            if isinstance(element_value_list, list):
                for inner_dict in element_value_list:
                    if isinstance(inner_dict, dict):
                        url_list = inner_dict.get("url")
                        # 检查 url_list 是否为列表并且包含元素
                        if isinstance(url_list, list) and url_list:
                            has_content = True
                            break # 找到一个有内容的URL即可跳出内部循环
            
            if has_content:
                elements_with_content_url.append(element_key)

        print(f"文件: {file_path}")
        print(f"总元素数量: {total_elements}")
        print(f"URL有内容的元素数量: {len(elements_with_content_url)}")
        print("URL有内容的元素列表:")
        # 为了避免输出过长，可以选择只打印部分或者询问用户
        if len(elements_with_content_url) > 50:
             print(f"(列表过长，仅显示前50个)")
             for key in elements_with_content_url[:50]:
                 print(f"- {key}")
        else:
            for key in elements_with_content_url:
                print(f"- {key}")


    except FileNotFoundError:
        print(f"错误：文件 {file_path} 未找到。", file=sys.stderr)
    except json.JSONDecodeError:
        print(f"错误：无法解析文件 {file_path} 中的 JSON 数据。", file=sys.stderr)
    except Exception as e:
        print(f"处理文件 {file_path} 时发生未知错误: {e}", file=sys.stderr)

if __name__ == "__main__":
    target_file = "data/cache/fusion/fusion_cache_mm_0512.json"
    process_fusion_cache(target_file) 