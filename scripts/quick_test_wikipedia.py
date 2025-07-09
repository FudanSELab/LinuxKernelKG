#!/usr/bin/env python3
"""
快速测试脚本：验证Wikipedia API优化是否生效
简单快速的测试，用于验证基本功能是否正常
"""

import asyncio
import sys
import os
import time
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.entity_linker_ban import EntityLinker
from config.pipeline_config import PipelineConfig
from models.entity import Entity

async def quick_test():
    """快速测试函数"""
    print("=" * 50)
    print("Wikipedia API 快速测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # 使用保守的配置
    config = PipelineConfig()
    config.WIKIPEDIA_RATE_LIMIT = {
        'max_requests_per_minute': 12,  # 每分钟12次，很保守
        'max_requests_per_hour': 720,   # 每小时720次
        'min_request_interval': 3.0,    # 最少3秒间隔
        'retry_max_attempts': 3,
        'retry_base_delay': 5.0,
        'retry_max_delay': 60.0
    }
    
    # 创建简单的测试实体
    test_entities = [
        Entity(
            name="Linux",
            context="Linux operating system kernel",
            feature_id=1001
        ),
        Entity(
            name="process",
            context="Process management in operating systems",
            feature_id=1002
        )
    ]
    
    # 添加commit_ids到实体
    test_entities[0].commit_ids = ["test001"]
    test_entities[1].commit_ids = ["test002"]
    
    print(f"配置的限流设置: {config.WIKIPEDIA_RATE_LIMIT['max_requests_per_minute']}/分钟")
    print(f"测试实体数量: {len(test_entities)}")
    print("-" * 50)
    
    start_time = time.time()
    success_count = 0
    error_count = 0
    
    try:
        async with EntityLinker(config) as linker:
            for i, entity in enumerate(test_entities, 1):
                print(f"\n[{i}/{len(test_entities)}] 测试实体: {entity.name}")
                print(f"上下文: {entity.context}")
                
                entity_start = time.time()
                
                try:
                    linked_entities = await linker.link_entity(entity)
                    entity_time = time.time() - entity_start
                    
                    if linked_entities and len(linked_entities) > 0:
                        success_count += 1
                        linked_entity = linked_entities[0]
                        print(f"✓ 成功链接 (耗时: {entity_time:.2f}s)")
                        
                        # 显示链接结果
                        if hasattr(linked_entity, 'external_links') and 'wikipedia' in linked_entity.external_links:
                            print(f"  Wikipedia URL: {linked_entity.external_links['wikipedia'][0]}")
                        if hasattr(linked_entity, 'description') and linked_entity.description:
                            print(f"  描述: {linked_entity.description[:100]}...")
                    else:
                        print(f"- 未找到匹配 (耗时: {entity_time:.2f}s)")
                        
                except Exception as e:
                    error_count += 1
                    entity_time = time.time() - entity_start
                    print(f"✗ 链接失败 (耗时: {entity_time:.2f}s): {e}")
                
                # 显示API统计
                if hasattr(linker, 'api_stats'):
                    stats = linker.api_stats
                    print(f"  API统计: 总请求{stats['total_requests']}, 失败{stats['failed_requests']}, 限流{stats['rate_limited_requests']}")
    
    except Exception as e:
        print(f"严重错误: {e}")
        error_count += len(test_entities)
    
    # 测试结果
    total_time = time.time() - start_time
    
    print("\n" + "=" * 50)
    print("测试结果:")
    print(f"- 总测试数: {len(test_entities)}")
    print(f"- 成功链接: {success_count}")
    print(f"- 失败次数: {error_count}")
    print(f"- 总耗时: {total_time:.2f}s")
    print(f"- 平均耗时: {total_time/len(test_entities):.2f}s/实体")
    
    # 判断测试结果
    if error_count == 0:
        print("\n✓ 快速测试通过！系统运行正常")
        print("建议: 可以开始正式使用，但请持续监控API统计")
    elif success_count > 0:
        print(f"\n⚠ 部分测试通过 ({success_count}/{len(test_entities)})")
        print("建议: 进一步降低请求频率或检查网络连接")
    else:
        print("\n✗ 测试失败！请检查配置和网络连接")
        print("建议: 检查Wikipedia API可访问性")
    
    print(f"测试完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(quick_test()) 