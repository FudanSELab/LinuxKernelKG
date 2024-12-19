import sys
from pathlib import Path
import asyncio
import json

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from config.pipeline_config import PipelineConfig
from pipeline.entity_processor import EntityProcessor
from utils.logger import setup_logger

async def test_entity_linking():
    logger = setup_logger('test_entity_linking')
    config = PipelineConfig()
    
    # 测试数据
    test_entities = [
        "VM", 
        "virtual memory",
        "page fault handler",
        "THP",
        "memory pool"
    ]
    
    # 测试上下文
    test_context = """
    Linux kernel's memory management subsystem handles virtual memory allocation,
    page fault handling, and transparent huge pages support. It includes various
    components for efficient memory resource management.
    """
    
    logger.info("Starting entity linking test")
    logger.info(f"Test entities: {test_entities}")
    
    # 初始化处理器
    processor = EntityProcessor(config)
    
    try:
        # 执行实体链接
        results = await processor.process_linking_batch(test_entities)
        
        # 保存结果用于分析
        output_file = 'data/test/entity_linking_test_results.json'
        Path('data/test').mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'input': {
                    'entities': test_entities,
                    'context': test_context
                },
                'results': results
            }, f, ensure_ascii=False, indent=2)
            
        # 打印结果统计
        linked_count = sum(1 for r in results if r.get('linked_entity'))
        logger.info(f"\nTest Results Summary:")
        logger.info(f"Total entities: {len(test_entities)}")
        logger.info(f"Successfully linked: {linked_count}")
        logger.info(f"Linking rate: {linked_count/len(test_entities)*100:.2f}%")
        
        # 打印详细结果
        logger.info("\nDetailed Results:")
        for result in results:
            # 假设result是一个字典，包含mention、linked_entity和confidence字段
            mention = result.get('mention', '')
            linked_to = result.get('linked_entity', '')
            confidence = result.get('confidence', 0.0)
            
            if linked_to and confidence:
                logger.info(f"Entity: {mention:25} -> {linked_to:30} (confidence: {confidence:.2f})")
            else:
                logger.info(f"Entity: {mention:25} -> LINKING FAILED")
            
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(test_entity_linking())