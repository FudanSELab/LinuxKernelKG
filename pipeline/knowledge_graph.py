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
        
        all_results = {
            'linking': [],
            'fusion': []
        }
        
        # 先处理所有批次的实体链接
        for batch in batches:
            # 实体链接
            linking_results = await self.process_linking_batch(batch)
            all_results['linking'].extend(linking_results)
            
            # 获取未链接的实体
            unlinked_entities = [
                entity for entity, result in zip(batch, linking_results)
                if not result.get('linked_entity')
            ]
            
            # 对未链接实体进行融合
            if unlinked_entities:
                fusion_results = await self.process_fusion_batch(unlinked_entities)
                all_results['fusion'].extend(fusion_results)
        
        return all_results
        
    async def process_linking_batch(self, batch):
        """处理单个批次的实体链接"""
        return await self.entity_processor.process_linking_batch(batch)
        
    async def process_fusion_batch(self, batch):
        """处理单个批次的实体融合"""
        return await self.entity_processor.process_fusion_batch(batch)