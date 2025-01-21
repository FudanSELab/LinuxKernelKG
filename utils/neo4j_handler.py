from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
import logging
import pymysql
import pandas as pd
from utils.logger import setup_logger

class EnhancedNeo4jHandler:
    def __init__(self, **config):
        self.logger = logging.getLogger(__name__)
        
        # 从配置中提取认证信息
        auth = (config.pop('user', 'neo4j'), config.pop('password', 'cloudfdse'))
        uri = config.pop('uri', 'bolt://localhost:7687')
        
        self.logger.info(f"Connecting to Neo4j at {uri}")
        try:
            # 使用正确的参数创建驱动
            self.driver = GraphDatabase.driver(
                uri, 
                auth=auth,
                max_connection_pool_size=50,
                **config
            )
            # 立即测试连接
            self.driver.verify_connectivity()
            self.logger.info("Successfully connected to Neo4j database")
            
        except ServiceUnavailable as e:
            self.logger.error(f"Could not connect to Neo4j at {uri}")
            self.logger.error("Please check if:")
            self.logger.error("1. Docker container is running (docker ps)")
            self.logger.error("2. Ports are correctly mapped (7687)")
            self.logger.error("3. Container logs for any issues (docker logs neo4j-server)")
            raise ServiceUnavailable(
                f"Could not connect to Neo4j at {uri}. "
                "Please check if the Docker container is running and ports are correctly mapped."
            ) from e
            
        except AuthError as e:
            self.logger.error(f"Authentication failed for user '{auth[0]}'")
            self.logger.error("Please check if:")
            self.logger.error("1. Username matches NEO4J_AUTH environment variable")
            self.logger.error("2. Password matches NEO4J_AUTH environment variable")
            raise AuthError(
                f"Authentication failed for user '{auth[0]}'. "
                "Please check if credentials match Docker environment variables."
            ) from e
            
    def close(self):
        """关闭Neo4j连接"""
        if hasattr(self, 'driver'):
            self.driver.close()
            
    def __enter__(self):
        """支持上下文管理器"""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持上下文管理器"""
        self.close()
        
    def setup_constraints_and_indexes(self):
        """设置Neo4j约束和索引"""
        with self.driver.session() as session:
            try:
                # 创建唯一约束 - 使用新的语法
                session.run("""
                    CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
                    FOR (e:Entity)
                    REQUIRE e.id IS UNIQUE
                """)
                
                # 创建索引 - 使用新的语法
                session.run("""
                    CREATE INDEX entity_name_index IF NOT EXISTS
                    FOR (e:Entity)
                    ON (e.name)
                """)
                
                self.logger.info("Successfully created constraints and indexes")
                
            except Exception as e:
                self.logger.error(f"Error creating constraints and indexes: {str(e)}")
                raise
    
    def import_entity(self, entity_data):
        # 使用 name 作为唯一标识符，如果没有提供 id
        entity_id = entity_data.get('id', entity_data['name'])
        with self.driver.session() as session:
            session.run("""
                MERGE (e:Entity {name: $name})
                SET e += $properties
            """, {
                'name': entity_data['name'],
                'properties': entity_data
            })
    
    def import_relationship(self, from_id, to_id, rel_type, properties=None):
        with self.driver.session() as session:
            session.run("""
                MATCH (a:Entity {id: $from_id})
                MATCH (b:Entity {id: $to_id})
                MERGE (a)-[r:$rel_type]->(b)
                SET r += $properties
            """, {
                'from_id': from_id,
                'to_id': to_id,
                'rel_type': rel_type,
                'properties': properties or {}
            })
    
    def update_entity_properties(self, entity_id, properties):
        with self.driver.session() as session:
            session.run("""
                MATCH (e:Entity {id: $id})
                SET e += $properties
            """, {
                'id': entity_id,
                'properties': properties
            })
    
    def merge_entities(self, primary_id, secondary_ids):
        with self.driver.session() as session:
            # 转移所有关系到主实体
            session.run("""
                MATCH (primary:Entity {id: $primary_id})
                MATCH (secondary:Entity)
                WHERE secondary.id IN $secondary_ids
                OPTIONAL MATCH (secondary)-[r]->(other)
                WHERE NOT other:Entity OR other.id <> $primary_id
                WITH primary, secondary, r, other
                CALL apoc.merge.relationship(primary, type(r), r.properties, other)
                YIELD rel
                RETURN count(*)
            """, {
                'primary_id': primary_id,
                'secondary_ids': secondary_ids
            })
            
            # 删除次要实体
            session.run("""
                MATCH (e:Entity)
                WHERE e.id IN $secondary_ids
                DETACH DELETE e
            """, {
                'secondary_ids': secondary_ids
            })

    async def get_related_entities(self, entities):
        """获取与给定实体相关的所有实体
        TODO: 根据实际数据结构实现
        """
        return []

    async def find_fusion_group(self, entity):
        """查找实体是否存在于已有的融合组中
        TODO: 根据实际数据结构实现
        """
        return None

    async def get_known_synonyms(self, entity):
        """获取实体的已知同义词
        TODO: 根据实际数据结构实现
        """
        return []

    async def get_historical_fusions(self, entity):
        """获取实体的历史融合记录
        TODO: 根据实际数据结构实现
        """
        return []

    async def update_fusion_group(self, fusion_group):
        """更新或创建融合组
        TODO: 根据实际数据结构实现
        """
        pass

    async def add_synonym_relation(self, canonical, variation, confidence):
        """添加同义词关系
        TODO: 根据实际数据结构实现
        """
        pass

    def store_triple(self, head_entity, relation, tail_entity):
        """Store a valid triple in the Neo4j database."""
        relation_type = relation.upper().replace(' ', '_')
        
        # 使用动态关系类型的简单版本
        query = f"""
        MERGE (head:Entity {{name: $head_entity}})
        MERGE (tail:Entity {{name: $tail_entity}})
        MERGE (head)-[r:{relation_type}]->(tail)
        """
        with self.driver.session() as session:
            session.run(
                query, 
                head_entity=head_entity,
                tail_entity=tail_entity
            )

    def triple_exists(self, head_entity, relation, tail_entity):
        """
        检查三元组是否已存在于Neo4j数据库中
        
        Args:
            head_entity (str): 头实体
            relation (str): 关系
            tail_entity (str): 尾实体
            
        Returns:
            bool: 如果三元组存在返回True，否则返回False
        """
        # 将关系转换为Neo4j可接受的格式
        relation_type = relation.upper().replace(' ', '_')
        
        # 使用格式化字符串构建查询，关系类型直接嵌入查询中
        query = f"""
            MATCH (h:Entity {{name: $head_entity}})-[r:{relation_type}]->(t:Entity {{name: $tail_entity}})
            RETURN COUNT(r) > 0 as exists
        """
        
        with self.driver.session() as session:
            result = session.run(
                query,
                head_entity=head_entity,
                tail_entity=tail_entity
            )
            return result.single()["exists"]

class KnowledgeGraphSyncManager:
    def __init__(self, config, neo4j_handler):
        self.config = config
        self.neo4j = neo4j_handler
        self.logger = setup_logger()
        
    async def sync_from_mysql(self):
        """从MySQL同步数据到Neo4j"""
        connection = pymysql.connect(**self.config.DB_CONFIG)
        try:
            with connection.cursor() as cursor:
                cursor.execute(self.config.QUERY_MM_SQL)
                features = cursor.fetchall()
                
                for feature in features:
                    # 处理特性数据
                    await self._process_feature(feature)
                    
        finally:
            connection.close()
    
    async def sync_from_excel(self, excel_file):
        """从Excel文件同步数据到Neo4j"""
        df = pd.read_excel(excel_file)
        for _, row in df.iterrows():
            await self._process_excel_row(row)
    
    async def _process_feature(self, feature):
        # 实现特性处理逻辑
        pass
    
    async def _process_excel_row(self, row):
        # 实现Excel行处理逻辑
        pass

class KnowledgeGraphConfig:
    def __init__(self):
        self.neo4j_config = {
            'uri': 'bolt://localhost:7687',
            'user': 'neo4j',
            'password': 'password'
        }
        
        self.sync_settings = {
            'batch_size': 1000,
            'retry_attempts': 3,
            'sync_interval': 3600  # 每小时同步一次
        }
        
        self.entity_types = [
            'Concept',
            'Function',
            'Module',
            'Component'
        ]
        
        self.relationship_types = [
            'IMPLEMENTS',
            'DEPENDS_ON',
            'PART_OF',
            'RELATES_TO'
        ]