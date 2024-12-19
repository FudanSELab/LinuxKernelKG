import asyncio
from utils.logger import setup_logger
from pipeline.quality_assurance import QualityMonitor
from pipeline.entity_processor import EntityProcessor
from datetime import datetime

class KnowledgeGraphBuilder:
    def __init__(self, config, quality_monitor=None):
        self.logger = setup_logger()
        self.config = config
        self.quality_monitor = quality_monitor or QualityMonitor(config)
        self.entity_processor = EntityProcessor(config)
        
    async def process(self, features):
        """异步处理实体识别和匹配"""
        # 质量检查
        if not self.quality_monitor.check_extraction_quality(features):
            self.logger.warning("Extraction quality check failed")
        
        # 获取所有实体
        entities = []
        for feature in features:
            if 'entities' in feature:
                entities.extend(feature['entities'])
        
        # 批量处理
        batch_size = self.config.BATCH_SIZE
        batches = [entities[i:i + batch_size] 
                  for i in range(0, len(entities), batch_size)]
        
        # 并行处理所有批次
        all_results = await asyncio.gather(
            *[self.process_batch(batch) for batch in batches]
        )
        
        # 合并结果
        return self._merge_batch_results(all_results)
        
    async def process_batch(self, batch):
        """处理单个批次的实体"""
        # 并行执行实体融合和链接
        fusion_task = self.fuse_entities(batch)
        linking_task = self.link_entities(batch)
        
        fusion_result, linking_result = await asyncio.gather(fusion_task, linking_task)
        
        return {
            'fusion': fusion_result,  # 匹配到的实体概念
            'linking': linking_result # 链接到的外部知识
        }
        
    def _merge_batch_results(self, batch_results):
        """合并所有批次的结果"""
        merged = {
            'fusion': [],
            'linking': []
        }
        
        for result in batch_results:
            merged['fusion'].extend(result['fusion'])
            merged['linking'].extend(result['linking'])
            
        return merged

    async def fuse_entities(self, entities):
        """异步方法：实体融合"""
        return self.entity_processor.process_fusion_batch(entities)
    
    async def link_entities(self, entities):
        """异步方法：实体链接"""
        return await self.entity_processor.process_linking_batch(entities)