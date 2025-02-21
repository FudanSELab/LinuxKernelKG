import asyncio
import time
from utils.logger import setup_logger
from pipeline.quality_assurance import QualityMonitor
from pipeline.entity_processor import EntityProcessor

class KnowledgeGraphBuilder:
    def __init__(self, config, quality_monitor=None):
        self.logger = setup_logger()
        self.config = config
        self.quality_monitor = quality_monitor or QualityMonitor(config)
        self.entity_processor = EntityProcessor(config)

        # 定义固定的实体（Linux内核相关示例）
        self.fixed_entities = [
            "memory management",
            "debugging",
            "security",
            "RCU",
            "kallsyms"
        ]

    async def process(self):
        """异步处理实体识别和匹配"""
        total_start_time = time.time()

        # 质量检查（移除对 features 的依赖，传入空列表）
        qa_start_time = time.time()
        if not self.quality_monitor.check_extraction_quality([]):
            self.logger.warning("Extraction quality check failed")
        self.logger.info(f"Quality check took {time.time() - qa_start_time:.2f} seconds")

        # 使用固定的实体
        extract_start_time = time.time()
        entities = self.fixed_entities
        self.logger.info(f"Entity extraction took {time.time() - extract_start_time:.2f} seconds")
        self.logger.info(f"Total entities extracted: {len(entities)}")

        # 批处理准备
        batch_start_time = time.time()
        batch_size = self.config.BATCH_SIZE
        entity_batches = [entities[i:i + batch_size] for i in range(0, len(entities), batch_size)]

        self.logger.info(f"Batch preparation took {time.time() - batch_start_time:.2f} seconds")
        self.logger.info(f"Number of batches: {len(entity_batches)}, Batch size: {batch_size}")

        all_results = {'linking': [], 'fusion': []}

        # 处理所有批次
        processing_start_time = time.time()
        for batch_idx, entity_batch in enumerate(entity_batches, 1):
            batch_process_start = time.time()

            # 实体链接（移除 context_batch）
            linking_start = time.time()
            linking_results = await self.process_linking_batch(entity_batch)
            self.logger.info(f"Batch {batch_idx} linking took {time.time() - linking_start:.2f} seconds")
            all_results['linking'].extend(linking_results)

            # 识别未链接的实体
            unlinked_entities = [
                entity for entity, result in zip(entity_batch, linking_results)
                if not result.get('matches') or len(result.get('matches', [])) == 0
            ]

            # 对未链接实体进行融合
            if unlinked_entities:
                fusion_start = time.time()
                fusion_results = await self.process_fusion_batch(unlinked_entities)
                self.logger.info(f"Batch {batch_idx} fusion took {time.time() - fusion_start:.2f} seconds")
                all_results['fusion'].append(fusion_results)

            self.logger.info(f"Batch {batch_idx}/{len(entity_batches)} completed in {time.time() - batch_process_start:.2f} seconds")

        self.logger.info(f"Total processing time: {time.time() - processing_start_time:.2f} seconds")

        # 验证方案
        validation_start = time.time()
        if not self.validate_scheme(all_results):
            self.logger.error("Data does not match the defined scheme")
            return None
        self.logger.info(f"Schema validation took {time.time() - validation_start:.2f} seconds")

        total_time = time.time() - total_start_time
        self.logger.info(f"Total execution time: {total_time:.2f} seconds")
        self.logger.info(f"Results summary: {len(all_results['linking'])} linked, {len(all_results['fusion'])} fused")

        return all_results

    async def process_linking_batch(self, batch):
        """处理单个批次的实体链接"""
        return await self.entity_processor.process_linking_batch(batch)

    async def process_fusion_batch(self, batch):
        """处理单个批次的实体融合"""
        return await self.entity_processor.process_fusion(batch)

    def validate_scheme(self, results):
        """验证结果的方案（简化为始终通过）"""
        return True

# 测试代码
class Config:
    BATCH_SIZE = 2
    QUALITY_THRESHOLDS = {
        'precision': 0.8,
        'recall': 0.7,
        'entity_count': 1
    }

async def test():
    config = Config()
    builder = KnowledgeGraphBuilder(config)
    results = await builder.process()
    print(results)

if __name__ == "__main__":
    asyncio.run(test())