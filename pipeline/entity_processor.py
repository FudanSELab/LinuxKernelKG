from utils.logger import setup_logger
from pipeline.entity_linker import EntityLinker
from pipeline.entity_fusion import EntityFusion
from utils.neo4j_handler import EnhancedNeo4jHandler
from utils.fusion_cache import FusionCache

class EntityProcessor:
    def __init__(self, config):
        self.logger = setup_logger('entity_processor')
        self.config = config
        
        # 验证 neo4j_config 是否存在
        if not hasattr(self.config, 'neo4j_config'):
            raise ValueError("Missing neo4j_config in pipeline configuration")
        
        self.entity_linker = EntityLinker(config)
        self.entity_fusion = EntityFusion(config)
        
        # try:
        #     self.db_handler = EnhancedNeo4jHandler(**config.neo4j_config)
        #     self.db_handler.driver.verify_connectivity()
        #     self.logger.info("Successfully connected to Neo4j database")
        # except Exception as e:
        #     self.logger.error(f"Failed to initialize Neo4j connection: {str(e)}")
        #     raise

        self.fusion_cache = FusionCache()

    async def process_linking_batch(self, entities, contexts, feature_ids=None, commit_ids_list=None):
        """批量处理实体链接"""
        results = []
        for i, (entity, context) in enumerate(zip(entities, contexts)):
            feature_id = feature_ids[i] if feature_ids else None
            commit_ids = commit_ids_list[i] if commit_ids_list else None
            
            result = await self.entity_linker.link_entity(
                entity, 
                context,
                feature_id=feature_id,
                commit_ids=commit_ids
            )
            results.append(result)
        return results

    async def process_fusion(self, new_entities, feature_ids=None, commit_ids_list=None):
        """处理实体融合的入口方法
        
        Args:
            new_entities (list): 需要进行融合的新实体列表
            feature_ids (list, optional): 与实体一一对应的特征ID列表
            commit_ids_list (list, optional): 与实体一一对应的提交ID列表的列表
            
        Returns:
            dict: 包含融合结果的字典
        """
        # 直接调用 EntityFusion 类的处理方法
        return await self.entity_fusion.process_fusion(
            new_entities,
            feature_ids=feature_ids,
            commit_ids_list=commit_ids_list
        )

    