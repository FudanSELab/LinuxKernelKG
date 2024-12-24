import pandas as pd
import json

def update_excel_with_mentions(excel_path, json_path):
    # 读取Excel文件
    df = pd.read_excel(excel_path)
    
    # 读取JSON文件
    with open(json_path, 'r', encoding='utf-8') as f:
        mention_data = json.load(f)
    
    # 创建mention到feature_id和commit_ids的映射
    mention_map = {
        item['mention']: {
            'feature_id': item['feature_id'],
            'commit_ids': item['commit_ids']
        }
        for item in mention_data
    }
    
    # 添加新列
    df['feature_id'] = df['original_mention'].map(
        lambda x: mention_map.get(x, {}).get('feature_id', '')
    )
    df['commit_ids'] = df['original_mention'].map(
        lambda x: mention_map.get(x, {}).get('commit_ids', [])
    )
    
    # 保存更新后的文件
    df.to_excel(excel_path, index=False)
    print(f"Successfully updated {excel_path}")
    
    # 显示统计信息
    print(f"\nTotal rows: {len(df)}")
    print("\nSample rows after update:")
    print(df[['mention_id', 'original_mention', 'feature_id', 'commit_ids']].head())
    
    # 显示匹配统计
    matched = df['feature_id'].notna().sum()
    print(f"\nMatched mentions: {matched}/{len(df)}")

# 执行更新
excel_path = "entity_links.xlsx"
json_path = "mention_info.json"
update_excel_with_mentions(excel_path, json_path)
