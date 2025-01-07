import sys
from pathlib import Path
import asyncio
import datetime
import json

# 在37.1的lkg环境运行
# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from utils.logger import setup_logger
from config.pipeline_config import KnowledgeGraphConfig, PipelineConfig
from pipeline.data_collector import DataCollector
from pipeline.feature_enhancer import FeatureEnhancer
from pipeline.extractor import EntityRelationExtractor
from pipeline.quality_assurance import QualityMonitor
from pipeline.knowledge_graph import KnowledgeGraphBuilder
from utils.neo4j_handler import EnhancedNeo4jHandler

async def run_pipeline():
    logger = setup_logger()
    logger.info("Starting knowledge graph pipeline")
    
    # 初始化配置
    pipeline_config = PipelineConfig()
    kg_config = KnowledgeGraphConfig()
    quality_monitor = QualityMonitor(pipeline_config)
    
    # 验证 Neo4j 配置
    try:
        pipeline_config.validate_neo4j_config()
        logger.info("Neo4j configuration validated successfully")
    except ValueError as e:
        logger.error(f"Invalid Neo4j configuration: {str(e)}")
        return
        
    # 验证Neo4j配置
    try:
        kg_config.validate_connection()
        logger.info("Neo4j configuration validated successfully")
    except ValueError as e:
        logger.error(f"Invalid Neo4j configuration: {str(e)}")
        return
        
    # 测试Neo4j连接
    try:
        with EnhancedNeo4jHandler(**kg_config.neo4j_config) as neo4j_handler:
            # 测试连接
            neo4j_handler.driver.verify_connectivity()
            logger.info("Successfully connected to Neo4j database")
            
            # 初始化配置
            quality_monitor = QualityMonitor(pipeline_config)
            
            # 创建输出目录和时间戳
            output_dir = Path("output")
            output_dir.mkdir(exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 设置Neo4j约束和索引
            neo4j_handler.setup_constraints_and_indexes()
            
            # 1. Feature收集
            logger.info("Step 1: Collecting features")
            collector = DataCollector(pipeline_config)
            features = collector.collect_features()
            
            # 处理每个feature
            for i, feature in enumerate(features):
                logger.info(f"Processing feature {i+1}/{len(features)}")
                
                # 2. 文本增强
                enhancer = FeatureEnhancer(pipeline_config)
                enhanced_feature = enhancer.enhance_features([feature])
                
                # 3. 实体和关系抽取
                # todo commit里面抽取mention 可以考虑一个一个抽取？
                extractor = EntityRelationExtractor(pipeline_config)
                extraction_result = extractor.extract_entities_and_relations(enhanced_feature)
                
                # 4. 知识图谱构建
                kg_builder = KnowledgeGraphBuilder(pipeline_config, quality_monitor)
                matching_result = await kg_builder.process(extraction_result)
                
                if matching_result is None:
                    continue  # Exit if the scheme validation failed
                
                # 5. 存储到Neo4j
                for entity in matching_result.get('entities', []):
                    neo4j_handler.import_entity(entity)
                
                for relation in matching_result.get('relations', []):
                    neo4j_handler.import_relationship(
                        relation['from_id'],
                        relation['to_id'],
                        relation['type'],
                        relation.get('properties')
                    )
                
                # 保存处理结果到JSON（用于后续分析）
                progress_file = output_dir / f"kg_results_{timestamp}.json"
                with open(progress_file, "a", encoding="utf-8") as f:
                    json.dump(matching_result, f, ensure_ascii=False, indent=2)
                    f.write("\n")
                
                logger.info(f"Progress saved to {progress_file}")
            
            logger.info("Knowledge graph pipeline completed successfully")
            
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(run_pipeline())
  