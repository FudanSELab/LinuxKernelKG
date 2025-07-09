#!/usr/bin/env python3
"""
示例：使用优化后的实体链接器处理Wikipedia API 429限流
演示如何使用新的限流机制和重试策略
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.entity_linker_ban import EntityLinker
from config.pipeline_config import PipelineConfig
from models.entity import Entity

async def main():
    """演示优化后的实体链接功能"""
    
    # 初始化配置（使用更保守的设置）
    config = PipelineConfig()
    
    # 可以在运行时调整配置
    config.WIKIPEDIA_RATE_LIMIT = {
        'max_requests_per_minute': 15,  # 非常保守的设置
        'max_requests_per_hour': 900,   # 每小时最多900次请求
        'min_request_interval': 3.0,    # 每次请求间隔至少3秒
        'retry_max_attempts': 5,        # 最多重试5次
        'retry_base_delay': 3.0,        # 基础重试延迟3秒
        'retry_max_delay': 180.0        # 最大重试延迟3分钟
    }
    
    # 使用异步上下文管理器确保正确清理资源
    async with EntityLinker(config) as linker:
        # 准备测试实体
        test_entities = [
            Entity(
                name="process",
                context="Linux kernel process management and scheduling",
                feature_id=4001
            ),
            Entity(
                name="memory management",  
                context="Virtual memory and page allocation in Linux kernel",
                feature_id=4002
            ),
            Entity(
                name="file system",
                context="File system operations and VFS layer",
                feature_id=4003
            )
        ]
        
        # 添加commit_ids到实体
        test_entities[0].commit_ids = ["abc123"]
        test_entities[1].commit_ids = ["def456"]
        test_entities[2].commit_ids = ["ghi789"]
        
        print("=== 开始优化后的实体链接演示 ===")
        print(f"配置的限流设置: {config.WIKIPEDIA_RATE_LIMIT['max_requests_per_minute']}/分钟")
        print(f"请求间隔: {config.WIKIPEDIA_RATE_LIMIT['min_request_interval']}秒")
        print("=" * 50)
        
        # 处理实体
        total_linked = 0
        for i, entity in enumerate(test_entities, 1):
            print(f"\n处理实体 {i}/{len(test_entities)}: {entity.name}")
            print(f"上下文: {entity.context[:100]}...")
            
            try:
                linked_entities = await linker.link_entity(entity)
                
                if linked_entities:
                    total_linked += len(linked_entities)
                    for linked_entity in linked_entities:
                        print(f"✓ 成功链接: {linked_entity.name}")
                        if hasattr(linked_entity, 'external_links') and 'wikipedia' in linked_entity.external_links:
                            print(f"  Wikipedia: {linked_entity.external_links['wikipedia'][0]}")
                        if hasattr(linked_entity, 'description') and linked_entity.description:
                            print(f"  描述: {linked_entity.description[:100]}...")
                else:
                    print("✗ 未找到匹配的Wikipedia页面")
                    
            except Exception as e:
                print(f"✗ 处理失败: {e}")
                continue
                
            # 显示当前API统计
            linker.log_api_stats()
            
        print("\n" + "=" * 50)
        print(f"=== 处理完成，共链接了 {total_linked} 个实体 ===")
        
        # 最终统计将在退出上下文管理器时自动显示

if __name__ == "__main__":
    asyncio.run(main()) 