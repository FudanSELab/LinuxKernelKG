import pandas as pd

def process_excel_file(input_file):
    # 读取Excel文件
    try:
        df = pd.read_excel(input_file)
        
        # 保存实体名列表到文件
        with open('entity_names.txt', 'w', encoding='utf-8') as f:
            for entity in df.iloc[:, 0].tolist():
                if pd.notna(entity):
                    f.write(f"{str(entity).strip()}\n")
        
        # 创建新的DataFrame用于存储处理后的数据
        output_df = pd.DataFrame(columns=[
            'mention_id',
            'original_mention', 
            'overall_linkable',
            'ngram_linkable',
            'overall_wikipedia_link',
            'ngram_wikipedia_link'
        ])
        
        # 处理每一行数据
        for idx, row in df.iterrows():
            entity = str(row.iloc[0]).strip()
            if pd.notna(entity):
                mention_id = idx + 1
                # 检查第5列和第7列是否有链接
                has_col5_link = len(row) > 4 and pd.notna(row.iloc[4])
                has_col7_links = len(row) > 6 and pd.notna(row.iloc[6])
                
                # 获取第5列链接
                col5_link = str(row.iloc[4]).strip() if has_col5_link else ""
                
                # 获取第7列链接并处理成所需格式
                col7_links = []
                if has_col7_links:
                    links = str(row.iloc[6]).split()
                    for link in links:
                        if link.strip():
                            col7_links.append({
                                "ngram_mention": entity,
                                "wikipedia_link": link.strip()
                            })
                
                # 添加到DataFrame
                output_df.loc[len(output_df)] = [
                    mention_id,
                    entity,
                    has_col5_link,
                    has_col7_links, 
                    col5_link,
                    str(col7_links)
                ]
        
        # 保存为Excel文件
        output_file = 'entity_links.xlsx'
        output_df.to_excel(output_file, index=False)
        print(f"已保存处理后的数据到 {output_file}")

    except Exception as e:
        print(f"处理文件时出错: {str(e)}")

if __name__ == "__main__":
    input_file = "entity_link.xlsx"  # 替换为你的Excel文件名
    process_excel_file(input_file)