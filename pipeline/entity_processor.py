from utils.logger import setup_logger
from utils.deepseek import deepseek
from prompts.link import linkPrompt
from utils.utils import strip_json
import json
import asyncio
from pipeline.entity_linker import EntityLinker
from utils.neo4j_handler import EnhancedNeo4jHandler  # 修改导入路径

class EntityProcessor:
    def __init__(self, config):
        self.logger = setup_logger('entity_processor')
        self.config = config
        
        # 验证 neo4j_config 是否存在
        if not hasattr(self.config, 'neo4j_config'):
            raise ValueError("Missing neo4j_config in pipeline configuration")
        
        self.entity_linker = EntityLinker(config)
        
        try:
            self.db_handler = EnhancedNeo4jHandler(**config.neo4j_config)
            # 测试连接
            self.db_handler.driver.verify_connectivity()
            self.logger.info("Successfully connected to Neo4j database")
        except Exception as e:
            self.logger.error(f"Failed to initialize Neo4j connection: {str(e)}")
            raise
        
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
        
    async def process_fusion(self, new_entities, linked_entities=None):
        """处理实体融合
        
        Args:
            new_entities: 新发现的未链接实体列表
            linked_entities: 可选，已知的链接实体列表
        """
        # 1. 从数据库获取所有相关的已链接实体
        db_linked_entities = await self.db_handler.get_linked_entities(new_entities)
        
        # 2. 合并所有已链接实体
        all_linked_entities = set(db_linked_entities)
        if linked_entities:
            all_linked_entities.update(linked_entities)
        
        # 3. 处理每个未链接实体的融合
        fusion_results = []
        for entity in new_entities:
            # 对每个未链接实体，尝试与已链接实体进行融合
            fusion_group = await self._process_single_entity_fusion(entity, list(all_linked_entities))
            if fusion_group:
                fusion_results.append(fusion_group)
                # 更新数据库
                await self._update_database_with_fusion(fusion_group)
                
        return fusion_results
        
    async def _build_fusion_pool(self, new_entities, linked_entities=None):
        """构建融合候选池
        
        包含：
        1. 新发现的所有实体
        2. 已链接的实体
        3. 从数据库查询的相关实体
        """
        fusion_pool = set(new_entities)
        
        # 添加已链接实体
        if linked_entities:
            fusion_pool.update(linked_entities)
            
        # 从数据库获取相关实体
        db_entities = await self.db_handler.get_related_entities(new_entities)
        fusion_pool.update(db_entities)
        
        return list(fusion_pool)
        
    async def _process_single_entity_fusion(self, entity, linked_entities):
        """处理单个未链接实体的融合
        
        Args:
            entity: 未链接的实体
            linked_entities: 已链接实体列表
        """
        # 1. 查找候选项（只从已链接实体中查找）
        candidates = await self._find_all_fusion_candidates(entity, linked_entities)
        
        # 2. LLM验证
        verified_matches = []
        for candidate in candidates:
            if await self._verify_fusion_pair(entity, candidate):
                verified_matches.append(candidate)
                
        if verified_matches:
            # 找到匹配的已链接实体，创建融合组
            matched_entity = verified_matches[0]  # 选择第一个匹配的已链接实体
            # 查找该已链接实体的现有融合组
            existing_group = await self.db_handler.find_fusion_group(matched_entity)
            
            if existing_group:
                # 将新实体添加到现有融合组
                return self._merge_fusion_groups(existing_group, [entity])
            else:
                # 创建新的融合组
                return {
                    'original': matched_entity,
                    'variations': [entity],
                    'canonical_form': self._select_canonical_form([matched_entity, entity])
                }
        
        return None
        
    async def _find_all_fusion_candidates(self, entity, fusion_pool):
        """查找所有可能的融合候选项
        
        包括：
        1. 启发式规则匹配
        2. 数据库中的已知同义词
        3. 历史融合记录
        """
        candidates = set()
        
        # 启发式规则匹配
        rule_candidates = await self._find_fusion_candidates(entity, fusion_pool)
        candidates.update(rule_candidates)
        
        # 查询数据库中的同义词
        db_synonyms = await self.db_handler.get_known_synonyms(entity)
        candidates.update(db_synonyms)
        
        # 查询历史融合记录
        historical_synonyms = await self.db_handler.get_historical_fusions(entity)
        candidates.update(historical_synonyms)
        
        return list(candidates - {entity})
        
    async def _update_database_with_fusion(self, fusion_group):
        """将融合结果更新到数据库"""
        try:
            # 更新实体关系
            await self.db_handler.update_fusion_group(fusion_group)
            
            # 更新同义词关系
            canonical = fusion_group['canonical_form']
            for variation in fusion_group['variations']:
                await self.db_handler.add_synonym_relation(
                    canonical, 
                    variation,
                    confidence=1.0  # 可以根据验证结果调整置信度
                )
                
            self.logger.info(f"Successfully updated fusion group for {fusion_group['original']}")
            
        except Exception as e:
            self.logger.error(f"Failed to update database with fusion results: {str(e)}")
            raise
            
    def _merge_fusion_groups(self, existing_group, new_synonyms):
        """合并已存在的融合组与新发现的同义词"""
        all_variations = set(existing_group['variations'])
        all_variations.update(new_synonyms)
        
        return {
            'original': existing_group['original'],
            'variations': list(all_variations),
            'canonical_form': self._select_canonical_form(
                [existing_group['original']] + list(all_variations)
            )
        }
        
    async def _generate_variations(self, entity):
        """生成实体的变体形式"""
        # 实现变体生成逻辑
        return [entity]  # 临时返回原始实体
        
    def _select_canonical_form(self, variations: list) -> str:
        """从变体中选择规范形式
        
        选择规则：
        1. 优先选择完整形式而不是缩写
        2. 优先选择官方文档中更常用的形式
        3. 如果无法判断，使用最长的形式
        
        Args:
            variations: 所有变体的列表，包括原始实体
            
        Returns:
            str: 选择的规范形式
        """
        if not variations:
            return ""
        
        # 按长度排序，最长的可能是完整形式
        sorted_vars = sorted(variations, key=len, reverse=True)
        
        # 检查是否有明显的缩写（全大写且较短）
        has_abbrev = any(v.isupper() and len(v) <= 5 for v in variations)
        
        if has_abbrev:
            # 如果有缩写，选择非缩写的最长形式
            for var in sorted_vars:
                if not (var.isupper() and len(var) <= 5):
                    return var
        
        # 默认返回最长的形式
        return sorted_vars[0]
        
    async def _find_fusion_candidates(self, entity: str, all_entities: list) -> list:
        """使用启发式规则找到可能的同义词候选
        
        Args:
            entity: 要查找同义词的实体
            all_entities: 所有未链接实体的列表
            
        Returns:
            list: 候选同义词列表
        """
        candidates = set()
        
        # 1. 大小写变体
        lower_entity = entity.lower()
        for other in all_entities:
            if other != entity and other.lower() == lower_entity:
                candidates.add(other)
        
        # 2. 常见缩写模式
        # 处理括号中的缩写，如 "Virtual Memory (VM)" 或 "VM (Virtual Memory)"
        if '(' in entity:
            main_part = entity.split('(')[0].strip()
            abbrev = entity.split('(')[1].rstrip(')').strip()
            for other in all_entities:
                if other == main_part or other == abbrev:
                    candidates.add(other)
        
        # 3. 驼峰命名和下划线分隔
        words = self._split_identifier(entity)
        if len(words) > 1:
            # 检查首字母缩写
            acronym = ''.join(word[0].upper() for word in words)
            for other in all_entities:
                if other == acronym:
                    candidates.add(other)
        
        # 4. 常见同义词替换
        # 例如：'handler' <-> 'handling', 'manager' <-> 'management'
        common_variations = {
            'handler': 'handling',
            'manager': 'management',
            'allocator': 'allocation',
            'scheduler': 'scheduling'
        }
        
        for word in words:
            for base, variation in common_variations.items():
                if word.lower() == base:
                    new_words = [w if w.lower() != base else variation for w in words]
                    new_entity = ' '.join(new_words)
                    if new_entity in all_entities:
                        candidates.add(new_entity)
                elif word.lower() == variation:
                    new_words = [w if w.lower() != variation else base for w in words]
                    new_entity = ' '.join(new_words)
                    if new_entity in all_entities:
                        candidates.add(new_entity)
        
        return list(candidates)

    def _split_identifier(self, identifier: str) -> list:
        """将标识符分解为单词列表
        
        处理以下情况：
        1. 驼峰命名: MyVariableName -> ['My', 'Variable', 'Name']
        2. 下划线分隔: my_variable_name -> ['my', 'variable', 'name']
        3. 混合情况: my_VariableName -> ['my', 'Variable', 'Name']
        """
        import re
        
        # 首先按下划线分割
        parts = identifier.split('_')
        
        words = []
        for part in parts:
            # 处理驼峰命名
            camel_words = re.findall('[A-Z][a-z]*|[a-z]+|[A-Z]{2,}(?=[A-Z][a-z]|\d|\W|$)|\d+', part)
            words.extend(camel_words)
        
        return words

    async def _verify_fusion_pair(self, entity1: str, entity2: str) -> bool:
        """使用 LLM 验证两个实体是否为同义词
        
        Args:
            entity1: 第一个实体
            entity2: 第二个实体
            
        Returns:
            bool: 如果是同义词返回 True，否则返回 False
        """
        prompt = f"""As a Linux kernel expert, determine if the following two terms refer to the exact same concept in the Linux kernel context.
        
        Term 1: {entity1}
        Term 2: {entity2}
        
        Consider:
        1. They must refer to exactly the same concept
        2. One might be an abbreviation or alternative representation of the other
        3. They must be used interchangeably in Linux kernel documentation
        
        Return ONLY 'yes' if they are synonyms, or 'no' if they are not.
        """
        
        try:
            response = await self._get_llm_response(prompt)
            return response.strip().lower() == 'yes'
        except Exception as e:
            self.logger.error(f"LLM verification failed for {entity1} and {entity2}: {str(e)}")
            return False