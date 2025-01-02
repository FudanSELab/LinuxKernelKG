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
        
        # 获取所有实体和上下文
        entities = []
        contexts = []
        feature_ids = []  # 新增：存储feature_ids
        commit_ids_list = []  # 新增：存储commit_ids
        
        for feature in features:
            if 'entities' in feature:
                feature_name = feature.get('name', '')
                feature_id = feature.get('id')  # 新增：获取feature_id
                commits = feature.get('commits', [])
                
                # 新增：获取当前feature的所有commit_ids
                commit_ids = [commit.get('id') for commit in commits]
                
                # 从commits字典列表中提取commit_subject
                commit_messages = "\n".join(
                    commit.get('commit_message', '') 
                    for commit in commits
                )
                context = f"feature_name: {feature_name}\n\n{commit_messages}"
                
                for entity in feature['entities']:
                    entities.append(entity)
                    contexts.append(context)
                    feature_ids.append(feature_id)  # 新增：为每个实体添加对应的feature_id
                    commit_ids_list.append(commit_ids)  # 新增：为每个实体添加对应的commit_ids
        
        # 批量处理
        batch_size = self.config.BATCH_SIZE
        entity_batches = [entities[i:i + batch_size] 
                       for i in range(0, len(entities), batch_size)]
        context_batches = [contexts[i:i + batch_size]
                        for i in range(0, len(contexts), batch_size)]
        
        all_results = {
            'linking': [],
            'fusion': []
        }
        
        # 先处理所有批次的实体链接
        for entity_batch, context_batch in zip(entity_batches, context_batches):
            # 实体链接
            linking_results = await self.process_linking_batch(entity_batch, context_batch, feature_ids, commit_ids_list)
            all_results['linking'].extend(linking_results)
            
            # 获取未链接的实体
            unlinked_entities = [
                entity for entity, result in zip(entity_batch, linking_results)
                if not result.get('linked_entity')
            ]
            
            # 对未链接实体进行融合
            if unlinked_entities:
                fusion_results = await self.process_fusion_batch(unlinked_entities)
                all_results['fusion'].extend(fusion_results)
        
        # Validate scheme within the process method
        if not self.validate_scheme(all_results):
            self.logger.error("Data does not match the defined scheme")
            return None  # Return None or handle as needed

        return all_results
        
    async def process_linking_batch(self, batch, context_batch, feature_ids, commit_ids_list):
        """处理单个批次的实体链接
        
        Args:
            batch: 实体批次列表
            context_batch: 对应的上下文信息列表
            feature_ids: 特征ID列表
            commit_ids_list: commit ID列表
        
        Returns:
            list: 实体链接结果列表
        """
        return await self.entity_processor.process_linking_batch(batch, context_batch, feature_ids, commit_ids_list)
        
    async def process_fusion_batch(self, batch):
        """处理单个批次的实体融合"""
        return await self.entity_processor.process_fusion(batch)

    def validate_scheme(self, results):
        """Validate the scheme of the results."""
        return self.quality_monitor.validate_scheme(results)