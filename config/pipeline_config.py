import jsonschema

class Neo4jConfig:
    """Neo4j配置基类"""
    DEFAULT_CONFIG = {
        'uri': 'bolt://localhost:7687',     # Docker映射的本地端口
        'user': 'neo4j',                    # Docker环境变量中配置的用户名
        'password': 'cloudfdse',            # Docker环境变量中配置的密码
        'max_connection_lifetime': 3600
    }

    @staticmethod
    def validate_config(config):
        """验证Neo4j连接配置"""
        required_fields = ['uri', 'user', 'password']
        missing_fields = [field for field in required_fields if not config.get(field)]
                
        if missing_fields:
            raise ValueError(
                f"Missing required Neo4j configuration fields: {', '.join(missing_fields)}"
            )
            
        # 验证URI格式
        uri = config['uri']
        if not uri.startswith(('bolt://', 'neo4j://')):
            raise ValueError(
                f"Invalid Neo4j URI format: {uri}. "
                "Must start with 'bolt://' or 'neo4j://'"
            )
            
        return True

class PipelineConfig:
    # 数据库配置
    DB_CONFIG = {
        'host': '10.176.34.96',
        'port': 3306,
        'user': 'root',
        'password': '3edc@WSX!QAZ',
        'database': 'linuxDatabase',
        'charset': 'utf8mb4'
    }
    
    # 处理配置
    BATCH_SIZE = 50
    MAX_RETRIES = 3
    
    # 质量阈值配置
    QUALITY_THRESHOLDS = {
        "consistency_score": 0.8,
        "evaluation_score": 0.7,
        "validation_score": 0.75
    }
    
    # 文件路径配置
    DATA_DIR = "data"
    FEATURES_DIR = f"{DATA_DIR}/features"
    LOGS_DIR = f"{DATA_DIR}/log"
    
    # LLM配置
    LLM_CONFIG = {
        "model": "deepseek-chat",
        "temperature": 0.7,
        "max_tokens": 2000
    } 

    # 实体链接中，n-gram 分割符配置
    NGRAM_DELIMITERS = " -_"

    # 访问 Wikipedia 的代理配置
    WIKIPEDIA_PROXY_URL = {
        "http": "http://127.0.0.1:7897",
        "https": "http://127.0.0.1:7897"
    }

    # JSON Schema definition
    SCHEME_DEFINITION = {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "type": {"type": "string"}
                    },
                    "required": ["id", "name", "type"]
                }
            },
            "relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from_id": {"type": "string"},
                        "to_id": {"type": "string"},
                        "type": {"type": "string"},
                        "properties": {"type": "object"}
                    },
                    "required": ["from_id", "to_id", "type"]
                }
            }
        },
        "required": ["entities", "relations"]
    }

    # Neo4j配置
    neo4j_config = Neo4jConfig.DEFAULT_CONFIG

    @classmethod
    def validate_neo4j_config(cls):
        """验证Neo4j配置"""
        return Neo4jConfig.validate_config(cls.neo4j_config)

class KnowledgeGraphConfig:
    """知识图谱配置类"""
    def __init__(self):
        self.neo4j_config = Neo4jConfig.DEFAULT_CONFIG

    def validate_connection(self):
        """验证Neo4j连接配置"""
        return Neo4jConfig.validate_config(self.neo4j_config)
