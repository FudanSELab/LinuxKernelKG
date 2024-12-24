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
        auth = (config.pop('user', 'neo4j'), config.pop('password', ''))
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
        with self.driver.session() as session:
            session.run("""
                MERGE (e:Entity {id: $id})
                SET e += $properties
            """, {
                'id': entity_data['id'],
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