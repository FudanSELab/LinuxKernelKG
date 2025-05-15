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

    async def process_linking_batch(self, entities):
        """
        批量处理实体链接
        
        Args:
            entities (list): 需要进行链接的Entity对象列表
            
        Returns:
            list: 返回处理后的Entity对象列表，每个对象可能包含新增的外部链接
        """
        linked_entities = []
        for entity in entities:
            # entity_linker.link_entity 返回已处理的Entity对象列表
            processed_entities = await self.entity_linker.link_entity(entity)
            linked_entities.extend(processed_entities)
    
        return linked_entities

    async def process_fusion(self, new_entities, linked_entities=[]):
        """处理实体融合的入口方法
        
        Args:
            new_entities (list): 需要进行融合的新实体列表
            linked_entities (list, optional): 已链接的实体列表
            
        Returns:
            dict: 包含融合结果的字典
        """
        # 直接调用 EntityFusion 类的处理方法
        return await self.entity_fusion.process_fusion(
            new_entities,
            linked_entities
        )

    