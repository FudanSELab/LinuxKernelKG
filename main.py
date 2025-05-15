import sys
from pathlib import Path
import asyncio
import datetime
import json
import pymysql
import random
import csv
import pandas as pd
from models.feature import Feature
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
    # try:
    with EnhancedNeo4jHandler(**kg_config.neo4j_config) as neo4j_handler:
        # 测试连接 
        neo4j_handler.driver.verify_connectivity()
        logger.info("Successfully connected to Neo4j database")
        
        # 初始化配置
        quality_monitor = QualityMonitor(pipeline_config)
        
        # 创建输出目录和时间戳
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H")
        
        # 设置Neo4j约束和索引
        neo4j_handler.setup_constraints_and_indexes()
        
        # 1. Feature收集
        logger.info("Step 1: Collecting features")
        collector = DataCollector(pipeline_config)
        features = collector.collect_features()
        
        # # 随机抽取300个feature并保存
        # # 确保抽样数量不超过总数
        # sample_size = min(300, len(features))
        # sampled_features = random.sample(features, sample_size)
        
        # 准备保存抽样数据的文件
        # sample_file = output_dir / f"sampled_features_{timestamp}.csv"
        
        # # 将抽样数据保存为CSV
        # df = pd.DataFrame([{
        #     'feature_id': feature.feature_id,
        #     'h1': feature.h1,
        #     'h2': feature.h2,
        #     'feature_description': feature.feature_description,
        #     'version': feature.version
        # } for feature in features])
        
        # df.to_csv(sample_file, index=False, encoding='utf-8')
        # logger.info(f"Saved {sample_size} randomly sampled features to {sample_file}")
        
        # 设置起始位置
        start_index = 0
        logger.info(f"Starting processing from feature index {start_index}")
        kg_builder = KnowledgeGraphBuilder(pipeline_config, quality_monitor)
        # 处理每个feature
        for i, feature in enumerate(features[start_index:], start=start_index):
            logger.info(f"Processing feature {i+1}/{len(features)}")
            
            # # 2. 文本增强
            # enhancer = FeatureEnhancer(pipeline_config)
            # enhanced_feature = enhancer.enhance_features([feature])
            
            # 3. 实体和关系抽取
            extractor = EntityRelationExtractor(pipeline_config)
            extractor.extract_entities_and_relations(feature)
            
            # 新增：保存每个mention的数据
            # mentions_file = output_dir / f"feature_mentions_{timestamp}.csv"
            # mentions_data = []
            
            # # 收集所有mention数据
            # for entity in feature.entities:
            #     mentions_data.append({
            #         'feature_id': feature.feature_id,
            #         'mention': entity.name,
            #         'h1': feature.h1,
            #         'h2': feature.h2,
            #         'feature_description': feature.feature_description,
            #         'version': feature.version
            #         })
            
            # # 保存为CSV或追加到现有文件
            # if mentions_data:
            #     mentions_df = pd.DataFrame(mentions_data)
                
            #     # 如果文件已存在则追加，否则创建新文件
            #     if mentions_file.exists():
            #         mentions_df.to_csv(mentions_file, mode='a', header=False, index=False, encoding='utf-8')
            #     else:
            #         mentions_df.to_csv(mentions_file, index=False, encoding='utf-8')
                
            #     logger.info(f"Saved {len(mentions_data)} mentions for feature {feature.feature_id}")

            # continue
            # 4. 知识图谱构建
            matching_result = await kg_builder.process(feature)
            
            if matching_result is None:
                continue  # Exit if the scheme validation failed
            
            # 5. 存储到Neo4j
            # 处理链接结果
            # for linked_entity in matching_result.get('linking', []):
            #     matches = linked_entity.get('matches', [])
            #     for match in matches:
            #         try:
            #             entity_data = {
            #                 'name_en': match['linked_entity'],
            #                 'rel_desc': feature.get('feature_description', ''),
            #                 'source': match.get('wikipedia_url', ''),
            #                 'feature_id': [feature.get('feature_id', '')],
            #                 'wikidata_id': match.get('wikidata_id', ''),
            #                 'type': 'link',
            #                 'class': match.get('class', '')
            #             }
            #             logger.info(f"Storing linked entity: {entity_data['name_en']}")
            #             collector.store_entity(entity_data)
            #         except ValueError as e:
            #             logger.error(f"Failed to store linked entity: {str(e)}")
            #             continue
            
            # # 处理融合结果
            # for fusion_groups in matching_result.get('fusion', []):
            #     for fusion_group in fusion_groups:
            #         try:
            #             source_data = json.dumps(fusion_group.get('reference', ''))
            #             if len(source_data) > 1024:
            #                 source_data = "reference too long"
            #             entity_data = {
            #                 'name_en': fusion_group.get('canonical_form', ''),
            #                 'rel_desc': feature.get('feature_description', ''),
            #                 'feature_id': [feature.get('feature_id', '')],
            #                 'aliases': [{'name_en': v} for v in fusion_group.get('variations', [])],
            #                 'source': source_data,
            #                 'type': 'fusion',
            #                 'class': fusion_group.get('class', '')
            #             }
            #             logger.info(f"Storing fused entity: {entity_data['name_en']}")
            #             collector.store_entity(entity_data)
            #         except ValueError as e:
            #             logger.error(f"Failed to store fused entity: {str(e)}")
            #             continue

            # 新增：验证三元组有效性
            validate_triples(feature.triples, collector, neo4j_handler, logger)

            # 保存处理结果到JSON（用于后续分析）
            # progress_file = output_dir / f"kg_results_{timestamp}.json"
            # with open(progress_file, "a", encoding="utf-8") as f:
            #     json.dump(matching_result, f, ensure_ascii=False, indent=2)
            #     f.write("\n")
            
            # logger.info(f"Progress saved to {progress_file}")
        
        logger.info("Knowledge graph pipeline completed successfully")
            
    # except Exception as e:
    #     logger.error(f"Failed to connect to Neo4j: {str(e)}")
    #     raise

def validate_triples(triples, collector, neo4j_handler, logger):
    """验证三元组的有效性"""
    for triple in triples:
        head_entity = triple[0]
        relation = triple[1]
        tail_entity = triple[2]

        # 查询数据库以验证三元组的有效性
        if collector.db.entity_exists(head_entity) and collector.db.entity_exists(tail_entity):
            # 检查三元组是否已存在
            if not neo4j_handler.triple_exists(head_entity, relation, tail_entity):
                # 如果三元组有效且不存在，将其存入Neo4j数据库
                logger.info(f"Storing new triple: {head_entity} -> {relation} -> {tail_entity}")
                neo4j_handler.store_triple(head_entity, relation, tail_entity)
            else:
                logger.info(f"Triple already exists: {head_entity} -> {relation} -> {tail_entity}")
        else:
            logger.info(f"Invalid triple: {head_entity} - {relation} > {tail_entity}")

if __name__ == "__main__":
    asyncio.run(run_pipeline())
  