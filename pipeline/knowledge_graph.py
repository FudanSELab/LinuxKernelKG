import asyncio
import time
from utils.logger import setup_logger
from pipeline.quality_assurance import QualityMonitor
from pipeline.entity_processor import EntityProcessor
from datetime import datetime
from utils.db import DB
from models.feature import Feature
from models.entity import Entity

class KnowledgeGraphBuilder:
    def __init__(self, config, quality_monitor=None):
        self.logger = setup_logger()
        self.config = config
        self.quality_monitor = quality_monitor or QualityMonitor(config)
        self.entity_processor = EntityProcessor(config)
        self.db = DB(config)
        
    async def process(self, feature):
        """异步处理实体识别和匹配
        
        Args:
            feature: Feature对象
            
        Returns:
            dict: 包含处理结果的字典
        """
        total_start_time = time.time()
        
        # 质量检查
        # qa_start_time = time.time()
        # if not self.quality_monitor.check_extraction_quality(features):
        #     self.logger.warning("Extraction quality check failed")
        # self.logger.info(f"Quality check took {time.time() - qa_start_time:.2f} seconds")
        
        # 获取所有实体和上下文
        extract_start_time = time.time()
        entities = feature.entities
        if entities:
            feature_description = feature.feature_description
            feature_id = feature.feature_id
            commits = feature.commits
            
            # 获取当前feature的所有commit_ids
            commit_ids = [commit.get('id') for commit in commits]
            
            # 从commits字典列表中提取commit_subject
            commit_messages = "\n".join(
                commit.get('commit_message', '') 
                for commit in commits
            )
            # context = f"feature_description: {feature_description}\n\n{commit_messages}"
            
            for entity in feature.entities:
                entity.set_context_by_feature_description(feature_description)
     
        self.logger.info(f"Entity extraction took {time.time() - extract_start_time:.2f} seconds")
        
        # 批量处理
        batch_start_time = time.time()
        batch_size = self.config.BATCH_SIZE
        entity_batches = [entities[i:i + batch_size] 
                       for i in range(0, len(entities), batch_size)]
        # context_batches = [contexts[i:i + batch_size]
        #                 for i in range(0, len(contexts), batch_size)]
        
        self.logger.info(f"Batch preparation took {time.time() - batch_start_time:.2f} seconds")
        self.logger.info(f"Number of batches: {len(entity_batches)}, Batch size: {batch_size}")
        
        all_results = {
            'linking': [],
            'fusion': [],
            'triples': []
        }
        
        # 处理所有批次
        processing_start_time = time.time()
        batch_count = 0
        
        for entity_batch in entity_batches:
            batch_count += 1
            batch_process_start = time.time()
            
            # 实体链接
            linking_start = time.time()
            linking_results = await self.process_linking_batch(entity_batch)
            linking_time = time.time() - linking_start
            self.logger.info(f"Batch 链接{batch_count} took {linking_time:.2f} seconds")
            
            all_results['linking'].extend(linking_results)
            
            # 一次遍历同时获取未链接和已链接的实体
            unlinked_entities = []
            linked_entities = []
            for entity in entity_batch:
                if entity.external_links:
                    linked_entities.append(entity)
                else:
                    unlinked_entities.append(entity)
            
            # 对未链接实体进行融合
            if unlinked_entities and linked_entities:
                fusion_start = time.time()
                fusion_results = await self.process_fusion_batch(unlinked_entities, linked_entities)
                fusion_time = time.time() - fusion_start
                self.logger.info(f"Batch {batch_count} fusion took {fusion_time:.2f} seconds")
                all_results['fusion'].append(fusion_results)
            
            self.logger.info(f"Batch 融合 {batch_count}/{len(entity_batches)} completed in {time.time() - batch_process_start:.2f} seconds")
        
        self.logger.info(f"Total processing time: {time.time() - processing_start_time:.2f} seconds")
        
        # 处理每个Feature中的triples
        if feature.triples:
            for triple in feature.triples:
                head_entity = triple[0]
                tail_entity = triple[2]

                # 查询数据库以验证三元组的有效性
                if self.query_entity_in_db(head_entity) and self.query_entity_in_db(tail_entity):
                    all_results['triples'].append(triple)
                        
        # Validate scheme
        validation_start = time.time()
        if not self.validate_scheme(all_results):
            self.logger.error("Data does not match the defined scheme")
            return None
        self.logger.info(f"Schema validation took {time.time() - validation_start:.2f} seconds")
        
        total_time = time.time() - total_start_time
        self.logger.info(f"Total execution time: {total_time:.2f} seconds")
        self.logger.info(f"Results summary: {len(all_results['linking'])} linked, {len(all_results['fusion'])} fused")
        
        return all_results
        
    async def process_linking_batch(self, batch):
        """处理单个批次的实体链接
        
        Args:
            batch: Entity对象批次列表
            context_batch: 对应的上下文信息列表
            feature_ids: 特征ID列表
            commit_ids_list: commit ID列表
        
        Returns:
            list: 实体链接结果列表
        """
        return await self.entity_processor.process_linking_batch(batch)
        
    async def process_fusion_batch(self, batch, linked_entities):
        """处理单个批次的实体融合
        
        Args:
            batch: 未链接的Entity对象列表
            linked_entities: 已链接的Entity对象列表
            feature_id: 特征ID列表
            commit_ids_list: commit ID列表
            
        Returns:
            dict: 融合结果
        """
        return await self.entity_processor.process_fusion(batch, linked_entities)

    def validate_scheme(self, results):
        """验证结果的模式
        
        Args:
            results: 处理结果
            
        Returns:
            bool: 验证结果
        """
        return True
        # return self.quality_monitor.validate_scheme(results)

    def query_entity_in_db(self, entity):
        """查询数据库以检查实体是否存在
        
        Args:
            entity: 要查询的实体
            
        Returns:
            bool: 实体是否存在
        """
        return self.db.entity_exists(entity)
