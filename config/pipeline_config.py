import jsonschema
from config.llm_config import LLMType

class Neo4jConfig:
    """Neo4j配置基类"""
    DEFAULT_CONFIG = {
        'uri': 'bolt://localhost:6103',     # Docker映射的本地端口
        'user': 'neo4j',                    # Docker环境变量中配置的用户名
        # 登录密码： neo4j@openspg
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
        LLMType.OPENAI: {
            "api_key": "sk-OIA8e1b5f9e53736bf8a045d17bb205403a6be38d49h7PYl",
            "base_url": "https://api.gptsapi.net/v1",
            "model": "gpt-4o-mini"
        },
        LLMType.DEEPSEEK: {
            "api_key": "sk-c875aefe59f5412a919c431bac6c7cea",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat"
        }
    }

    # 实体链接中，n-gram 分割符配置
    # 包含空格、连字符、下划线、点号、斜杠、反斜杠、逗号、分号、括号等常见分隔符
    NGRAM_DELIMITERS = " -_.,/\\;()[]{}|"

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

    # 添加 LLM 类型配置
    LLM_TYPE = LLMType.DEEPSEEK  # 修改为使用 DeepSeek

    # Wikipedia 本地数据库配置
    USE_LOCAL_WIKIPEDIA = False
    WIKIPEDIA_DB_PATH = 'data/wikipedia.db'

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
