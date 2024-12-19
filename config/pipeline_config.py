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
    
    # SQL查询
    QUERY_MM_SQL = """
    SELECT feature_id, text, version
        FROM newbies_feature
        WHERE h1 = 'Memory management' and version = '6.6'
        ORDER BY feature_id DESC;
    """
    
    QUERY_COMMIT_SQL = """
    SELECT id, commit_id FROM newbies_mapping
        WHERE feature_id = %s
        ORDER BY id ASC;
    """
    
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