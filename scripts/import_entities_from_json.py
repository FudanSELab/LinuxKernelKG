#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
实体数据导入脚本

从JSON文件中读取已链接的实体数据并批量导入到MySQL数据库中。
该脚本参考mysql_manager.py中的insert_entities_batch函数来实现数据导入。
"""

import json
import argparse
import sys
import os
from typing import List, Dict, Any
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.entity import Entity
from database.mysql_manager import MySQLManager
from config.pipeline_config import PipelineConfig
from utils.logger import setup_logger

logger = setup_logger('import_entities', file_output=True)

class EntityImporter:
    """实体数据导入器"""
    
    def __init__(self, config: PipelineConfig):
        """
        初始化导入器
        
        Args:
            config: 配置对象
        """
        self.config = config
        self.mysql_manager = MySQLManager(config)
        self.stats = {
            'total_entities': 0,
            'successful_imports': 0,
            'skipped_entities': 0,
            'failed_imports': 0,
            'start_time': None,
            'end_time': None
        }
    
    def load_entities_from_json(self, file_path: str) -> List[Entity]:
        """
        从JSON文件加载实体数据
        
        Args:
            file_path: JSON文件路径
            
        Returns:
            List[Entity]: 实体对象列表
        """
        entities = []
        
        try:
            logger.info(f"开始从 {file_path} 加载实体数据...")
            
            with open(file_path, 'r', encoding='utf-8') as file:
                # 加载整个JSON数组
                entities_data = json.load(file)
                
                if not isinstance(entities_data, list):
                    logger.error("JSON文件不是数组格式")
                    return []
                
                logger.info(f"JSON文件包含 {len(entities_data)} 个实体")
                
                # 转换为Entity对象
                for idx, entity_data in enumerate(entities_data):
                    try:
                        # 创建Entity对象
                        entity = Entity.from_dict(entity_data)
                        
                        # 手动设置external_links，因为from_dict可能没有正确处理
                        if 'external_links' in entity_data:
                            entity.external_links = entity_data['external_links']
                            
                        entities.append(entity)
                        
                        if (idx + 1) % 1000 == 0:
                            logger.info(f"已处理 {idx + 1}/{len(entities_data)} 个实体...")
                            
                    except Exception as e:
                        logger.error(f"创建Entity对象失败 (索引 {idx}): {e}")
                        logger.debug(f"问题数据: {entity_data}")
                        continue
            
            logger.info(f"成功加载 {len(entities)} 个实体")
            return entities
            
        except FileNotFoundError:
            logger.error(f"文件不存在: {file_path}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return []
        except Exception as e:
            logger.error(f"加载实体数据失败: {e}")
            return []
    
    def import_entities_batch(self, entities: List[Entity], batch_size: int = 100) -> Dict[str, int]:
        """
        批量导入实体到数据库
        
        Args:
            entities: 实体列表
            batch_size: 批处理大小
            
        Returns:
            Dict[str, int]: 导入统计信息
        """
        self.stats['total_entities'] = len(entities)
        self.stats['start_time'] = datetime.now()
        
        logger.info(f"开始批量导入 {len(entities)} 个实体，批处理大小: {batch_size}")
        
        # 分批处理
        for i in range(0, len(entities), batch_size):
            batch = entities[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(entities) + batch_size - 1) // batch_size
            
            logger.info(f"处理第 {batch_num}/{total_batches} 批 ({len(batch)} 个实体)...")
            
            try:
                # 使用mysql_manager的批量插入功能
                results = self.mysql_manager.insert_entities_batch(batch)
                
                # 统计结果
                for entity, eid in results:
                    if eid is not None:
                        self.stats['successful_imports'] += 1
                        logger.debug(f"成功导入实体: {entity.name} (eid: {eid})")
                    else:
                        self.stats['failed_imports'] += 1
                        logger.warning(f"导入失败: {entity.name}")
                
                # 显示进度
                processed = min(i + batch_size, len(entities))
                progress = (processed / len(entities)) * 100
                logger.info(f"进度: {processed}/{len(entities)} ({progress:.1f}%)")
                
            except Exception as e:
                logger.error(f"批处理失败 (第 {batch_num} 批): {e}")
                self.stats['failed_imports'] += len(batch)
        
        self.stats['end_time'] = datetime.now()
        return self.stats
    
    def print_import_stats(self):
        """打印导入统计信息"""
        if self.stats['start_time'] and self.stats['end_time']:
            duration = self.stats['end_time'] - self.stats['start_time']
            duration_str = str(duration).split('.')[0]  # 去掉微秒
        else:
            duration_str = "未知"
        
        logger.info("=" * 60)
        logger.info("导入统计信息:")
        logger.info(f"总实体数: {self.stats['total_entities']}")
        logger.info(f"成功导入: {self.stats['successful_imports']}")
        logger.info(f"跳过实体: {self.stats['skipped_entities']}")
        logger.info(f"导入失败: {self.stats['failed_imports']}")
        logger.info(f"成功率: {(self.stats['successful_imports'] / max(self.stats['total_entities'], 1)) * 100:.1f}%")
        logger.info(f"总耗时: {duration_str}")
        logger.info("=" * 60)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='从JSON文件导入实体数据到MySQL数据库')
    parser.add_argument(
        '--input', '-i',
        type=str,
        default='/home/fdse/ytest/LinuxKernelKG/output/entity_linking/linked_entities_gpt_0521.json',
        help='输入的JSON文件路径'
    )
    parser.add_argument(
        '--batch-size', '-b',
        type=int,
        default=100,
        help='批处理大小 (默认: 100)'
    )
    parser.add_argument(
        '--test-db',
        action='store_true',
        help='测试数据库连接并退出'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='只加载和验证数据，不写入数据库'
    )
    
    args = parser.parse_args()
    
    # 初始化配置和导入器
    config = PipelineConfig()
    importer = EntityImporter(config)
    
    # 测试数据库连接
    if args.test_db:
        logger.info("测试数据库连接...")
        if importer.mysql_manager.test_connection():
            logger.info("数据库连接测试成功！")
            return 0
        else:
            logger.error("数据库连接测试失败！")
            return 1
    
    # 检查输入文件
    if not os.path.exists(args.input):
        logger.error(f"输入文件不存在: {args.input}")
        return 1
    
    # 测试数据库连接
    logger.info("测试数据库连接...")
    if not importer.mysql_manager.test_connection():
        logger.error("数据库连接失败，请检查配置")
        return 1
    
    # 加载实体数据
    entities = importer.load_entities_from_json(args.input)
    if not entities:
        logger.error("没有加载到有效的实体数据")
        return 1
    
    # 如果是演练模式，只显示统计信息
    if args.dry_run:
        logger.info(f"演练模式: 加载了 {len(entities)} 个实体")
        logger.info("第一个实体示例:")
        logger.info(f"  名称: {entities[0].name}")
        logger.info(f"  特征ID: {entities[0].feature_id}")
        logger.info(f"  描述: {entities[0].description[:100]}...")
        return 0
    
    # 开始导入
    try:
        stats = importer.import_entities_batch(entities, args.batch_size)
        importer.print_import_stats()
        
        # 根据导入结果返回退出码
        if stats['failed_imports'] == 0:
            logger.info("所有实体导入成功！")
            return 0
        elif stats['successful_imports'] > 0:
            logger.warning("部分实体导入成功")
            return 0
        else:
            logger.error("所有实体导入失败")
            return 1
            
    except KeyboardInterrupt:
        logger.info("用户中断导入过程")
        importer.print_import_stats()
        return 1
    except Exception as e:
        logger.error(f"导入过程发生错误: {e}")
        return 1

if __name__ == "__main__":
    exit(main()) 