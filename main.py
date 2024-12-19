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
from config.pipeline_config import PipelineConfig
from pipeline.data_collector import DataCollector
from pipeline.feature_enhancer import FeatureEnhancer
from pipeline.extractor import EntityRelationExtractor
from pipeline.quality_assurance import QualityMonitor
from pipeline.knowledge_graph import KnowledgeGraphBuilder

async def run_pipeline():
    logger = setup_logger()
    logger.info("Starting knowledge graph pipeline")
    config = PipelineConfig()
    quality_monitor = QualityMonitor(config)
    
    # 创建输出目录和时间戳
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        # 1. Feature收集
        logger.info("Step 1: Collecting features")
        collector = DataCollector(config)
        features = collector.collect_features()  # 移除limit参数，让它返回所有features
        
        all_results = {
            'fusion': [],
            'linking': []
        }
        
        # 对每个feature单独处理
        for i, feature in enumerate(features):
            logger.info(f"Processing feature {i}/{len(features)}")
            
            # 2. 文本增强
            enhancer = FeatureEnhancer(config)
            enhanced_feature = enhancer.enhance_features([feature])
            
            # 3. 实体和关系抽取
            extractor = EntityRelationExtractor(config)
            extraction_result = extractor.extract_entities_and_relations(enhanced_feature)
            
            # 4. 知识图谱构建
            kg_builder = KnowledgeGraphBuilder(config, quality_monitor)
            matching_result = await kg_builder.process(extraction_result)
            
            # 合并结果
            all_results['fusion'].extend(matching_result['fusion'])
            all_results['linking'].extend(matching_result['linking'])
            
            # 保存当前进度
            progress_file = output_dir / f"kg_results_{timestamp}_progress_{i}.json"
            with open(progress_file, "w", encoding="utf-8") as f:
                json.dump(all_results, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Intermediate results saved to {progress_file}")
        
        # 保存最终结果
        final_file = output_dir / f"kg_results_{timestamp}_final.json"
        with open(final_file, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Final results saved to {final_file}")
        logger.info(f"Found {len(all_results['fusion'])} matched entities and {len(all_results['linking'])} external links")
        
        return all_results
        
    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}")
        raise
    
 

if __name__ == "__main__":
    asyncio.run(run_pipeline())  # 使用asyncio.run运行异步主函数
  