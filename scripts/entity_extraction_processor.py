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

def get_feature_by_id(file_path: str, feature_id: str) -> dict:
    """
    获取指定feature_id的信息
    
    Args:
        file_path: Excel文件路径
        feature_id: 要查询的feature_id
    
    Returns:
        dict: feature信息字典，如果未找到则返回None
    """
    features = collect_features_with_mentions(file_path)
    return features.get(feature_id)

def get_all_feature_stats(file_path: str) -> Dict[str, int]:
    """
    获取所有feature的统计信息
    
    Args:
        file_path: Excel文件路径
    
    Returns:
        Dict[str, int]: 包含统计信息的字典
    """
    features = collect_features_with_mentions(file_path)
    
    stats = {
        'total_features': len(features),
        'total_mentions': sum(data['mention_count'] for data in features.values()),
        'avg_mentions_per_feature': sum(data['mention_count'] for data in features.values()) / len(features) if features else 0
    }
    
    return stats

def print_feature_summary(file_path: str):
    """
    打印所有feature的摘要信息
    
    Args:
        file_path: Excel文件路径
    """
    features = collect_features_with_mentions(file_path)
    stats = get_all_feature_stats(file_path)
    
    print(f"总计有效feature数量: {stats['total_features']}")
    print(f"总mention数量: {stats['total_mentions']}")
    print(f"每个feature平均mention数量: {stats['avg_mentions_per_feature']:.2f}")
    
    print("\n各feature的mention数量:")
    for feature_id, data in features.items():
        print(f"Feature ID: {feature_id}, Mentions: {data['mention_count']}")

# 如果直接运行此脚本，则执行示例
if __name__ == "__main__":
    file_path = "data/mention_extraction_benchmark_0225.xlsx"
    print_feature_summary(file_path) 