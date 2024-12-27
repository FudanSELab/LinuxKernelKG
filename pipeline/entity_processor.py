from utils.logger import setup_logger
from utils.deepseek import deepseek
from prompts.link import linkPrompt
from utils.utils import strip_json
import json
import asyncio
from pipeline.entity_linker import EntityLinker

class EntityProcessor:
    def __init__(self, config):
        self.logger = setup_logger('entity_processor')
        self.config = config
        self.entity_linker = EntityLinker(config)
        
    async def process_linking_batch(self, entities, contexts, feature_ids=None, commit_ids_list=None):
        """批量处理实体链接"""
        results = []
        for i, (entity, context) in enumerate(zip(entities, contexts)):
            feature_id = feature_ids[i] if feature_ids else None
            commit_ids = commit_ids_list[i] if commit_ids_list else None
            
            result = await self.entity_linker.link_entity(
                entity, 
                context,
                feature_id=feature_id,
                commit_ids=commit_ids
            )
            results.append(result)
        return results
        
    async def process_fusion_batch(self, unlinked_entities):
        """处理未链接实体的融合"""
        self.logger.info(f"Processing fusion for {len(unlinked_entities)} unlinked entities")
        
        # 使用 LLM 进行实体融合
        fusion_results = []
        for entity in unlinked_entities:
            variations = await self._generate_variations(entity)
            fusion_group = {
                'original': entity,
                'variations': variations,
                'canonical_form': self._select_canonical_form(variations)
            }
            fusion_results.append(fusion_group)
            
        return fusion_results
        
    async def _generate_variations(self, entity):
        """生成实体的变体形式"""
        # 实现变体生成逻辑
        return [entity]  # 临时返回原始实体
        
    def _select_canonical_form(self, variations):
        """选择规范形式"""
        # 实现规范形式选择逻辑
        return variations[0]  # 临时返回第一个变体