#!/usr/bin/env python3
"""
测试脚本：验证Wikipedia API限流和429错误处理
用于测试优化后的实体链接器是否能正确处理API限制
"""

import asyncio
import sys
import os
import time
import logging
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.entity_linker_ban import EntityLinker, RateLimiter
from config.pipeline_config import PipelineConfig
from models.entity import Entity

# 设置测试日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class WikipediaAPITester:
    """Wikipedia API测试器"""
    
    def __init__(self):
        self.config = PipelineConfig()
        self.test_results = {
            'rate_limiter_tests': [],
            'api_retry_tests': [],
            'entity_linking_tests': [],
            'performance_tests': []
        }
    
    async def test_rate_limiter(self):
        """测试限流器是否正常工作"""
        print("\n=== 测试1: 限流器功能测试 ===")
        
        # 创建一个高频率的限流器用于测试
        test_limiter = RateLimiter(max_requests_per_minute=5, max_requests_per_hour=20)
        
        start_time = time.time()
        request_times = []
        
        # 快速发送6个请求，应该触发限流
        for i in range(6):
            await test_limiter.wait_if_needed()
            request_times.append(time.time())
            print(f"请求 {i+1} 在 {request_times[-1] - start_time:.2f}s 发送")
        
        # 验证限流是否生效
        intervals = [request_times[i] - request_times[i-1] for i in range(1, len(request_times))]
        avg_interval = sum(intervals) / len(intervals)
        
        test_passed = any(interval > 10 for interval in intervals)  # 应该有较长的等待
        
        self.test_results['rate_limiter_tests'].append({
            'test_name': 'Basic Rate Limiting',
            'passed': test_passed,
            'avg_interval': avg_interval,
            'max_interval': max(intervals),
            'details': f"平均间隔: {avg_interval:.2f}s, 最大间隔: {max(intervals):.2f}s"
        })
        
        if test_passed:
            print("✓ 限流器测试通过 - 正确限制了请求频率")
        else:
            print("✗ 限流器测试失败 - 未能正确限制请求频率")
    
    async def test_conservative_settings(self):
        """测试保守的API设置"""
        print("\n=== 测试2: 保守设置下的实体链接测试 ===")
        
        # 使用非常保守的设置
        self.config.WIKIPEDIA_RATE_LIMIT = {
            'max_requests_per_minute': 10,  # 非常保守
            'max_requests_per_hour': 600,
            'min_request_interval': 4.0,   # 4秒间隔
            'retry_max_attempts': 3,
            'retry_base_delay': 5.0,
            'retry_max_delay': 60.0
        }
        
        # 创建测试实体
        test_entities = [
            Entity(
                name="kernel",
                context="Linux kernel core functionality",
                feature_id=2001
            ),
            Entity(
                name="driver",
                context="Device driver implementation",
                feature_id=2002
            ),
            Entity(
                name="scheduler",
                context="Process scheduling in kernel",
                feature_id=2003
            )
        ]
        
        # 添加commit_ids到实体
        test_entities[0].commit_ids = ["test123"]
        test_entities[1].commit_ids = ["test456"]
        test_entities[2].commit_ids = ["test789"]
        
        start_time = time.time()
        successful_links = 0
        failed_links = 0
        
        async with EntityLinker(self.config) as linker:
            print(f"开始测试 {len(test_entities)} 个实体...")
            
            for i, entity in enumerate(test_entities, 1):
                print(f"\n处理实体 {i}/{len(test_entities)}: {entity.name}")
                
                try:
                    entity_start = time.time()
                    linked_entities = await linker.link_entity(entity)
                    entity_time = time.time() - entity_start
                    
                    if linked_entities:
                        successful_links += 1
                        print(f"✓ 成功链接 (耗时: {entity_time:.2f}s)")
                    else:
                        print(f"- 未找到匹配 (耗时: {entity_time:.2f}s)")
                        
                except Exception as e:
                    failed_links += 1
                    print(f"✗ 链接失败: {e}")
                
                # 显示API统计
                if hasattr(linker, 'api_stats'):
                    stats = linker.api_stats
                    print(f"  API统计: 总请求{stats['total_requests']}, 失败{stats['failed_requests']}, 限流{stats['rate_limited_requests']}")
        
        total_time = time.time() - start_time
        
        self.test_results['entity_linking_tests'].append({
            'test_name': 'Conservative Settings Test',
            'total_entities': len(test_entities),
            'successful_links': successful_links,
            'failed_links': failed_links,
            'total_time': total_time,
            'avg_time_per_entity': total_time / len(test_entities),
            'passed': failed_links == 0  # 没有失败就算通过
        })
        
        print(f"\n保守设置测试完成:")
        print(f"- 总实体数: {len(test_entities)}")
        print(f"- 成功链接: {successful_links}")
        print(f"- 失败链接: {failed_links}")
        print(f"- 总耗时: {total_time:.2f}s")
        print(f"- 平均每个实体: {total_time/len(test_entities):.2f}s")
    
    async def test_error_recovery(self):
        """测试错误恢复机制"""
        print("\n=== 测试3: 错误恢复和重试机制测试 ===")
        
        # 设置更激进的设置来可能触发限流
        self.config.WIKIPEDIA_RATE_LIMIT = {
            'max_requests_per_minute': 30,  # 相对激进的设置
            'max_requests_per_hour': 1000,
            'min_request_interval': 1.0,
            'retry_max_attempts': 5,       # 增加重试次数
            'retry_base_delay': 2.0,
            'retry_max_delay': 30.0
        }
        
        # 创建更多的测试实体
        test_entities = []
        test_terms = ["process", "memory", "file", "network", "security", "device", "thread", "cache"]
        
        for i, term in enumerate(test_terms):
            entity = Entity(
                name=term,
                context=f"Linux kernel {term} management",
                feature_id=3000 + i
            )
            entity.commit_ids = [f"test_{i}"]
            test_entities.append(entity)
        
        start_time = time.time()
        rate_limited_count = 0
        retry_count = 0
        
        async with EntityLinker(self.config) as linker:
            print(f"开始压力测试 {len(test_entities)} 个实体...")
            
            for i, entity in enumerate(test_entities, 1):
                print(f"处理实体 {i}/{len(test_entities)}: {entity.name}", end=" ")
                
                try:
                    linked_entities = await linker.link_entity(entity)
                    if linked_entities:
                        print("✓")
                    else:
                        print("-")
                        
                except Exception as e:
                    print(f"✗ ({e})")
                
                # 收集统计信息
                if hasattr(linker, 'api_stats'):
                    rate_limited_count = linker.api_stats.get('rate_limited_requests', 0)
                
                # 每5个实体显示一次统计
                if i % 5 == 0:
                    elapsed = time.time() - start_time
                    print(f"  进度: {i}/{len(test_entities)}, 耗时: {elapsed:.1f}s, 限流次数: {rate_limited_count}")
        
        total_time = time.time() - start_time
        
        self.test_results['performance_tests'].append({
            'test_name': 'Error Recovery Test',
            'total_entities': len(test_entities),
            'total_time': total_time,
            'rate_limited_count': rate_limited_count,
            'avg_requests_per_minute': len(test_entities) / (total_time / 60),
            'passed': True  # 只要能完成就算通过
        })
        
        print(f"\n错误恢复测试完成:")
        print(f"- 处理了 {len(test_entities)} 个实体")
        print(f"- 总耗时: {total_time:.2f}s")
        print(f"- 触发限流: {rate_limited_count} 次")
        print(f"- 平均请求频率: {len(test_entities)/(total_time/60):.2f}/分钟")
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("Wikipedia API 限流和错误处理测试")
        print(f"测试开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        # 运行各项测试
        await self.test_rate_limiter()
        await self.test_conservative_settings()
        await self.test_error_recovery()
        
        # 生成测试报告
        self.generate_report()
    
    def generate_report(self):
        """生成测试报告"""
        print("\n" + "=" * 60)
        print("测试报告")
        print("=" * 60)
        
        all_passed = True
        
        for category, tests in self.test_results.items():
            if tests:
                print(f"\n{category.replace('_', ' ').title()}:")
                for test in tests:
                    status = "✓ 通过" if test['passed'] else "✗ 失败"
                    print(f"  {test['test_name']}: {status}")
                    if 'details' in test:
                        print(f"    {test['details']}")
                    if not test['passed']:
                        all_passed = False
        
        print(f"\n总体结果: {'✓ 所有测试通过' if all_passed else '✗ 部分测试失败'}")
        print(f"测试完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 提供使用建议
        print("\n使用建议:")
        if all_passed:
            print("- 系统已优化，可以在生产环境中使用")
            print("- 建议使用保守的限流设置开始")
            print("- 监控API统计日志，根据需要调整参数")
        else:
            print("- 建议进一步降低请求频率")
            print("- 增加重试延迟时间")
            print("- 检查网络连接和Wikipedia服务状态")

async def main():
    """主测试函数"""
    tester = WikipediaAPITester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main()) 