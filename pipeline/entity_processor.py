from utils.logger import setup_logger
from utils.deepseek import deepseek
from prompts.link import linkPrompt
from utils.utils import strip_json
import json
import asyncio
from pipeline.entity_linker import EntityLinker

class EntityProcessor:
    def __init__(self, config):
        self.logger = setup_logger('entity_processor')
        self.config = config
        self.entity_linker = EntityLinker(config)
        
    def process_entities(self, verified_results):
        """处理实体，包括实体融合和链接"""
        self.logger.info("Starting entity processing")
        
        all_entities = []
        # 收集所有实体
        for result in verified_results:
            if 'entities' in result:
                all_entities.extend(result['entities'])
        
        # 实体融合
        self.logger.info(f"Processing fusion for {len(all_entities)} entities")
        fusion_results = self.process_fusion_batch(all_entities)
        
        # 实体链接
        self.logger.info("Processing entity linking")
        linking_results = self.process_linking_batch(all_entities)
        
        # 合并处理结果
        processed_results = self.merge_entity_results(
            verified_results, 
            fusion_results, 
            linking_results
        )
        
        return processed_results
        
    def process_fusion_batch(self, entities):
        """处理一批实体的融合"""
        self.logger.info(f"Processing fusion batch of {len(entities)} entities")
        # 实现实体融合的具体逻辑
        fusion_results = []
        # TODO: 使用LLM进行实体融合判断
        return fusion_results
    
    async def process_linking_batch(self, entities):
        """处理一批实体的链接"""
        self.logger.info(f"Processing linking batch of {len(entities)} entities")
        results = []
        
        # 获取实体的上下文（这里需要从配置或其他地方获取）
        context = self._get_entity_context()
        
        # 并行处理实体链接
        tasks = [
            self.entity_linker.link_entity(entity, context)
            for entity in entities
        ]
        
        # 等待所有链接任务完成
        results = await asyncio.gather(*tasks)
        
        return results
    
    def _get_entity_context(self):
        """获取实体的上下文信息"""
        # TODO: 实现从配置或其他地方获取上下文的逻辑
        return "Linux kernel memory management context"
    
    def _create_default_results(self, entities):
        """创建默认的未链接结果"""
        return [{
            'entity': entity,
            'linked': False,
            'linked_to': None
        } for entity in entities]
    
    def merge_entity_results(self, original_results, merged_entities, linked_entities):
        """合并处理结果到原始数据"""
        entity_mapping = self._create_entity_mapping(merged_entities, linked_entities)
        
        updated_results = []
        for result in original_results:
            updated_result = result.copy()
            if 'entities' in updated_result:
                updated_result['entities'] = [
                    entity_mapping.get(entity, entity) 
                    for entity in updated_result['entities']
                ]
            updated_results.append(updated_result)
            
        return updated_results
    
    def _create_entity_mapping(self, merged_entities, linked_entities):
        """创建实体映射字典"""
        mapping = {}
        # TODO: 根据融合和链接结果创建映射
        return mapping 