import sys
from pathlib import Path
import json

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from config.pipeline_config import PipelineConfig
from pipeline.extractor import EntityRelationExtractor
from utils.logger import setup_logger
from utils.db import DB

if __name__ == "__main__":
    # 读取配置
    config = PipelineConfig()
    logger = setup_logger(name="extractTest", level="INFO")
    db = DB(config)
    
    # 读取待处理的特征
    features = db.get_all_features()
    
    # 初始化实体关系抽取器
    extractor = EntityRelationExtractor(config)
    
    logger.info("Start extracting entities and relations...")

    # 抽取实体和关系
    features_output = extractor.extract_entities_and_relations(features, save_to_file=True)

    logger.info("All done!")