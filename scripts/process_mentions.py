import pandas as pd
from typing import Dict, List

def collect_features_with_mentions(file_path: str) -> Dict[str, dict]:
    """
    读取Excel文件并收集所有有mention的feature
    
    Args:
        file_path: Excel文件路径
    
    Returns:
        Dict[str, dict]: 包含feature信息和mentions的字典
        格式为: {
            'feature_id': {
                'h1': str,
                'h2': str,
                'feature_description': str,
                'version': str,
                'mentions': List[str],
                'mention_count': int
            }
        }
    """
    # 读取Excel文件
    df = pd.read_excel(file_path)
    
    # 初始化结果字典
    feature_data = {}
    current_feature_id = None
    
    # 遍历每一行
    for _, row in df.iterrows():
        # 如果当前行有feature_id，说明是新的feature
        if pd.notna(row['feature_id']):
            current_feature_id = str(row['feature_id'])
            feature_data[current_feature_id] = {
                'h1': row['h1'] if pd.notna(row['h1']) else "",
                'h2': row['h2'] if pd.notna(row['h2']) else "",
                'feature_description': row['feature_description'] if pd.notna(row['feature_description']) else "",
                'version': row['version'] if pd.notna(row['version']) else "",
                'mentions': []
            }
        
        # 如果有mention，添加到当前feature的mentions列表中
        if pd.notna(row['mention']) and current_feature_id is not None:
            feature_data[current_feature_id]['mentions'].append(row['mention'])
    
    # 过滤掉没有mention的feature_id
    filtered_feature_data = {
        feature_id: data for feature_id, data in feature_data.items() 
        if len(data['mentions']) > 0
    }
    
    # 添加mention计数
    for feature_id in filtered_feature_data:
        filtered_feature_data[feature_id]['mention_count'] = len(filtered_feature_data[feature_id]['mentions'])
    
    return filtered_feature_data

def main():
    file_path = "data/mention_extraction_benchmark_0225.xlsx"
    
    # 收集所有有mention的feature
    features = collect_features_with_mentions(file_path)
    
    # 打印结果统计
    print(f"Total features with mentions: {len(features)}")
    
    # 打印每个feature的信息和mention数量
    for feature_id, data in features.items():
        print(f"\nFeature ID: {feature_id}")
        print(f"H1: {data['h1']}")
        print(f"H2: {data['h2']}")
        print(f"Feature Description: {data['feature_description']}")
        print(f"Version: {data['version']}")
        print(f"Number of mentions: {data['mention_count']}")
        
        # 可选：打印所有mention
        print("Mentions:")
        for mention in data['mentions']:
            print(f"- {mention}")

if __name__ == "__main__":
    main() 