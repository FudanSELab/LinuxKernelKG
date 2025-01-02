import pandas as pd
import json

def check_json_column(file_path, column_index=6):  # 因为是第7列，索引为6
    try:
        # 读取 Excel 文件
        df = pd.read_excel(file_path)
        
        # 获取第7列数据
        column_data = df.iloc[:, column_index]
        
        print(f"开始检查第 {column_index + 1} 列的 JSON 格式")
        print("-" * 50)
        
        # 检查每一行
        for idx, value in enumerate(column_data, 1):
            try:
                # 将单引号替换为双引号（因为原代码中也有这个处理）
                if isinstance(value, str):
                    value = value.replace("'", '"')
                    json.loads(value)
                    print(f"第 {idx} 行: JSON 格式正确")
                else:
                    print(f"第 {idx} 行: 警告 - 值不是字符串类型，实际类型为 {type(value)}")
            except json.JSONDecodeError as e:
                print(f"第 {idx} 行: JSON 格式错误")
                print(f"错误信息: {str(e)}")
                print(f"问题数据: {value}")
                print("-" * 30)
                
    except Exception as e:
        print(f"读取文件时发生错误: {str(e)}")

if __name__ == "__main__":
    file_path = "/home/fdse/ytest/LinuxKernelKG/data/entity_link_benchmark_1231.xlsx"
    check_json_column(file_path)
