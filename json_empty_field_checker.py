#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON文件元素统计脚本
统计JSON文件中根级别元素的数量和有值元素数量
"""

import json
import os
import sys


def count_elements(data):
    """
    统计JSON根级别元素
    
    Args:
        data: JSON数据（字典）
        
    Returns:
        dict: 统计结果
    """
    if not isinstance(data, dict):
        raise ValueError("JSON根级别必须是对象类型")
    
    total_elements = len(data)
    non_empty_elements = 0
    empty_elements = 0
    
    # 遍历所有键值对
    for key, value in data.items():
        if isinstance(value, list) and len(value) > 0:
            non_empty_elements += 1
        else:
            empty_elements += 1
    
    return {
        'total_elements': total_elements,
        'non_empty_elements': non_empty_elements,
        'empty_elements': empty_elements
    }


def print_report(stats, filename):
    """
    打印统计报告
    
    Args:
        stats: 统计数据字典
        filename: 文件名
    """
    print("=" * 50)
    print(f"JSON文件元素统计报告: {filename}")
    print("=" * 50)
    
    total = stats['total_elements']
    non_empty = stats['non_empty_elements']
    empty = stats['empty_elements']
    
    if total > 0:
        non_empty_rate = (non_empty / total) * 100
        empty_rate = (empty / total) * 100
    else:
        non_empty_rate = 0
        empty_rate = 0
    
    print(f"总元素数: {total}")
    print(f"有值元素数: {non_empty} ({non_empty_rate:.2f}%)")
    print(f"空元素数: {empty} ({empty_rate:.2f}%)")
    print("=" * 50)


def main():
    """
    主函数
    """
    # 检查命令行参数
    if len(sys.argv) != 2:
        print("使用方法: python json_empty_field_checker.py <json_file_path>")
        print("示例: python json_empty_field_checker.py data/cache/fusion/fusion_cache_mm_0603_reference.json")
        sys.exit(1)
    
    json_file_path = sys.argv[1]
    
    # 检查文件是否存在
    if not os.path.exists(json_file_path):
        print(f"错误: 文件 '{json_file_path}' 不存在")
        sys.exit(1)
    
    try:
        # 加载JSON文件
        print(f"正在加载JSON文件: {json_file_path}")
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print("JSON文件加载成功，开始统计元素...")
        
        # 统计元素
        stats = count_elements(data)
        
        # 打印报告
        print_report(stats, os.path.basename(json_file_path))
        
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"数据格式错误: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"错误: 无法找到文件 '{json_file_path}'")
        sys.exit(1)
    except PermissionError:
        print(f"错误: 没有权限读取文件 '{json_file_path}'")
        sys.exit(1)
    except Exception as e:
        print(f"处理过程中发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()