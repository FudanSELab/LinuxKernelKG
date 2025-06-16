#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实体版本信息更新脚本
根据feature_id从参考文件中获取version信息，更新目标实体文件
"""

import json
import os
import sys
import shutil
from datetime import datetime
from typing import Dict, List, Any, Tuple


class EntityVersionUpdater:
    def __init__(self):
        # 配置文件路径
        self.reference_file = "output/entity_extraction/extraction_results_20250509_0958.jsonl"
        self.target_file = "output/entity_linking/linked_entities_gpt_mm_0508.json"
        self.backup_suffix = f"_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 统计信息
        self.stats = {
            'total_reference_records': 0,
            'total_target_entities': 0,
            'successful_updates': 0,
            'failed_updates': 0,
            'missing_feature_ids': 0,
            'duplicate_feature_ids': 0
        }
    
    def load_version_mapping(self) -> Dict[int, str]:
        """
        从JSONL参考文件中构建feature_id到version的映射字典
        
        Returns:
            Dict[int, str]: feature_id -> version映射字典
        """
        print(f"正在加载版本映射数据从: {self.reference_file}")
        
        if not os.path.exists(self.reference_file):
            raise FileNotFoundError(f"参考文件不存在: {self.reference_file}")
        
        version_mapping = {}
        
        try:
            with open(self.reference_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        record = json.loads(line)
                        feature_id = record.get('feature_id')
                        feature_info = record.get('feature', {})
                        version = feature_info.get('version')
                        
                        if feature_id is not None and version is not None:
                            if feature_id in version_mapping:
                                self.stats['duplicate_feature_ids'] += 1
                                print(f"警告: 发现重复的feature_id {feature_id} (行 {line_num})")
                            
                            version_mapping[feature_id] = version
                            self.stats['total_reference_records'] += 1
                        
                    except json.JSONDecodeError as e:
                        print(f"警告: 第{line_num}行JSON解析失败: {e}")
                        continue
                        
        except Exception as e:
            raise Exception(f"读取参考文件时发生错误: {e}")
        
        print(f"成功加载 {len(version_mapping)} 个feature_id->version映射")
        return version_mapping
    
    def load_target_entities(self) -> List[Dict[str, Any]]:
        """
        加载目标JSON文件中的实体数据
        
        Returns:
            List[Dict[str, Any]]: 实体对象列表
        """
        print(f"正在加载目标实体文件: {self.target_file}")
        
        if not os.path.exists(self.target_file):
            raise FileNotFoundError(f"目标文件不存在: {self.target_file}")
        
        try:
            with open(self.target_file, 'r', encoding='utf-8') as f:
                entities = json.load(f)
                
            if not isinstance(entities, list):
                raise ValueError("目标文件应包含实体对象数组")
            
            self.stats['total_target_entities'] = len(entities)
            print(f"成功加载 {len(entities)} 个实体对象")
            return entities
            
        except Exception as e:
            raise Exception(f"读取目标文件时发生错误: {e}")
    
    def create_backup(self) -> str:
        """
        创建目标文件的备份
        
        Returns:
            str: 备份文件路径
        """
        backup_path = self.target_file + self.backup_suffix
        
        try:
            shutil.copy2(self.target_file, backup_path)
            print(f"已创建备份文件: {backup_path}")
            return backup_path
            
        except Exception as e:
            raise Exception(f"创建备份文件失败: {e}")
    
    def update_entities_with_version(self, entities: List[Dict[str, Any]], 
                                   version_mapping: Dict[int, str]) -> List[Dict[str, Any]]:
        """
        为实体对象添加version字段
        
        Args:
            entities: 实体对象列表
            version_mapping: feature_id到version的映射字典
            
        Returns:
            List[Dict[str, Any]]: 更新后的实体对象列表
        """
        print("正在更新实体version字段...")
        
        updated_entities = []
        
        for i, entity in enumerate(entities):
            try:
                feature_id = entity.get('feature_id')
                
                if feature_id is None:
                    self.stats['missing_feature_ids'] += 1
                    print(f"警告: 实体 {i+1} 缺少feature_id字段")
                    # 添加空的version字段
                    entity['version'] = None
                    self.stats['failed_updates'] += 1
                else:
                    # 查找对应的version
                    version = version_mapping.get(feature_id)
                    
                    if version is not None:
                        entity['version'] = version
                        self.stats['successful_updates'] += 1
                    else:
                        print(f"警告: 未找到feature_id {feature_id} 对应的version信息")
                        entity['version'] = None
                        self.stats['failed_updates'] += 1
                
                updated_entities.append(entity)
                
                # 进度显示
                if (i + 1) % 500 == 0:
                    print(f"已处理 {i + 1}/{len(entities)} 个实体")
                    
            except Exception as e:
                print(f"警告: 处理实体 {i+1} 时发生错误: {e}")
                entity['version'] = None
                updated_entities.append(entity)
                self.stats['failed_updates'] += 1
        
        return updated_entities
    
    def save_updated_entities(self, entities: List[Dict[str, Any]]) -> None:
        """
        保存更新后的实体数据到目标文件
        
        Args:
            entities: 更新后的实体对象列表
        """
        print(f"正在保存更新后的数据到: {self.target_file}")
        
        try:
            with open(self.target_file, 'w', encoding='utf-8') as f:
                json.dump(entities, f, ensure_ascii=False, indent=2)
            
            print("文件保存成功")
            
        except Exception as e:
            raise Exception(f"保存文件时发生错误: {e}")
    
    def print_statistics(self) -> None:
        """输出处理统计信息"""
        print("\n" + "="*60)
        print("处理统计信息")
        print("="*60)
        print(f"参考文件记录数: {self.stats['total_reference_records']}")
        print(f"重复feature_id数: {self.stats['duplicate_feature_ids']}")
        print(f"目标实体总数: {self.stats['total_target_entities']}")
        print(f"成功更新数: {self.stats['successful_updates']}")
        print(f"更新失败数: {self.stats['failed_updates']}")
        print(f"缺少feature_id的实体数: {self.stats['missing_feature_ids']}")
        
        success_rate = (self.stats['successful_updates'] / self.stats['total_target_entities'] * 100 
                       if self.stats['total_target_entities'] > 0 else 0)
        print(f"成功率: {success_rate:.2f}%")
        print("="*60)
    
    def run(self) -> bool:
        """
        执行完整的版本更新流程
        
        Returns:
            bool: 处理是否成功
        """
        start_time = datetime.now()
        print(f"开始执行实体version更新任务 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # 1. 加载版本映射
            version_mapping = self.load_version_mapping()
            
            # 2. 加载目标实体
            entities = self.load_target_entities()
            
            # 3. 创建备份
            backup_path = self.create_backup()
            
            # 4. 更新实体version字段
            updated_entities = self.update_entities_with_version(entities, version_mapping)
            
            # 5. 保存更新后的数据
            self.save_updated_entities(updated_entities)
            
            # 6. 输出统计信息
            self.print_statistics()
            
            end_time = datetime.now()
            duration = end_time - start_time
            print(f"\n任务完成 - {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"总耗时: {duration.total_seconds():.2f} 秒")
            
            return True
            
        except Exception as e:
            print(f"\n错误: {e}")
            print("任务执行失败")
            return False


def main():
    """主函数"""
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
        print("使用说明:")
        print("python3 entity_version_updater.py")
        print("\n功能: 根据feature_id为实体添加version信息")
        print("输入文件: output/entity_extraction/extraction_results_20250509_0958.jsonl")
        print("目标文件: output/entity_linking/linked_entities_gpt_mm_0508.json")
        print("\n注意: 执行前会自动创建目标文件的备份")
        return
    
    updater = EntityVersionUpdater()
    success = updater.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main() 