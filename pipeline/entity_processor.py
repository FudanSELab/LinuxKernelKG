from utils.logger import setup_logger
from utils.deepseek import deepseek
from prompts.link import linkPrompt
from utils.utils import strip_json
import requests
import re
from pipeline.entity_linker import EntityLinker
from utils.neo4j_handler import EnhancedNeo4jHandler
import aiohttp
from utils.fusion_cache import FusionCache
from bs4 import BeautifulSoup
import asyncio

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

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
            self.db_handler.driver.verify_connectivity()
            self.logger.info("Successfully connected to Neo4j database")
        except Exception as e:
            self.logger.error(f"Failed to initialize Neo4j connection: {str(e)}")
            raise

        self.fusion_cache = FusionCache()

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

    async def process_fusion(self, new_entities, feature_ids=None, commit_ids_list=None):
        """处理实体融合的主流程
        
        处理流程：
        1. 预处理 - 标准化和去重
        2. 查找引用源 - 检查每个实体是否有官方文档或代码引用
        3. 基于引用源和上下文进行融合分析
        4. 评估结果
        
        Args:
            new_entities (list): 需要进行融合的新实体列表
            feature_ids (list, optional): 与实体一一对应的特征ID列表
            commit_ids_list (list, optional): 与实体一一对应的提交ID列表的列表
            
        Returns:
            dict: 包含融合结果的字典，格式如下：
            {
                'fusion_groups': [...],  # 融合组列表
                'stats': {               # 统计信息
                    'total_entities': int,
                    'total_groups': int,
                    'fusion_rate': float
                }
            }
        """
        # 1. 预处理 - 标准化和保留上下文信息
        processed_entities = self._preprocess_entities(new_entities, feature_ids, commit_ids_list)
        
        # 2. 查找每个实体的引用源，并分离有引用源的实体
        entities = {}
        entities_with_refs = {}  # 存储有引用源的实体
        entities_without_refs = {}  # 存储无引用源的实体

        for item in processed_entities:
            entity_name = item['entity']
            # 创建复合键
            entity_key = self._create_entity_key(
                entity_name,
                item['feature_id'],
                item['commit_ids']
            )

            reference = await self._find_entity_reference(
                entity_name,
                item['feature_id'],
                item['commit_ids']
            )

            # 根据引用源存在与否分组，使用复合键作为字典键
            if reference and reference['found']:
                if entity_name not in entities_with_refs:
                    entities_with_refs[entity_name] = {
                        'keys': set(),
                        'items': [],
                        'references': []  # 新增：存储引用信息
                    }
                entities_with_refs[entity_name]['keys'].add(entity_key)
                entities_with_refs[entity_name]['items'].append(item)
                entities_with_refs[entity_name]['references'].append(reference)  # 保存引用信息
            else:
                if entity_name not in entities_without_refs:
                    entities_without_refs[entity_name] = {
                        'keys': set(),
                        'items': [],
                        'references': []  # 新增：即使没有找到引用，也预留存储空间
                    }
                entities_without_refs[entity_name]['keys'].add(entity_key)
                entities_without_refs[entity_name]['items'].append(item)
                if reference:  # 如果有部分引用信息，也保存下来
                    entities_without_refs[entity_name]['references'].append(reference)
            
            # 在完整的实体字典中也保存引用信息
            item['references'] = reference
            entities[entity_key] = item

        # 现在评估引用获取的正确性
        self._evaluate_reference_accuracy(entities)

        # 3. 只处理有引用源的实体
        fusion_groups = []
        processed_entity_keys = set()  # 使用复合键跟踪已处理的实体

        for entity_name, entity_data in entities_with_refs.items():
            # 检查该实体的所有实例是否都已处理
            if entity_data['keys'].issubset(processed_entity_keys):
                continue
            
            # 获取融合候选项
            fusion_candidates = await self._get_fusion_candidates(
                entity_name,
                entities_with_refs,  # 只从有引用源的实体中寻找候选项
                processed_entity_keys,
                entity_data['items']
            )
            
            # 创建并存储融合组
            if fusion_candidates:
                group = self._create_fusion_group(
                    entity_name,
                    fusion_candidates,
                    entity_data['items'],
                    entity_data['items']
                )
                fusion_groups.append(group)
                
                # 更新已处理实体集合
                self._update_processed_entities(processed_entity_keys, entity_name, fusion_candidates)

        # 5. 计算统计信息
        stats = self._evaluate_fusion_results(fusion_groups)
        
        return {
            'fusion_groups': fusion_groups,
            'stats': stats
        }

    def _preprocess_entities(self, entities, feature_ids=None, commit_ids_list=None):
        """预处理实体，但不进行上下文去重
        - 只进行基础的标准化和清洗
        - 保留所有上下文信息供后续融合使用
        """
        processed = []
        
        for i, entity in enumerate(entities):
            normalized = self._normalize_entity_name(entity)
            if not normalized:
                continue
            
            entity_info = {
                'entity': normalized,
                'feature_id': feature_ids[i] if feature_ids else None,
                'commit_ids': commit_ids_list[i] if isinstance(commit_ids_list[i], list) else [commit_ids_list[i]] if commit_ids_list else None
            }
            processed.append(entity_info)
                
        return processed

    def _create_context_key(self, entity, feature_id, commit_ids):
        """创建包含上下文信息的唯一键"""
        if isinstance(commit_ids, list):
            commit_ids = sorted(commit_ids)  # 确保列表顺序一致
        return f"{entity}::{feature_id}::{','.join(commit_ids) if commit_ids else ''}"

    def _merge_context_info(self, existing_info, new_info):
        """合并具有相同上下文的实体信息"""
        # 可以根据需要合并或更新信息
        if new_info['commit_ids']:
            if isinstance(existing_info['commit_ids'], list):
                existing_info['commit_ids'].extend(new_info['commit_ids'])
            else:
                existing_info['commit_ids'] = [existing_info['commit_ids'], new_info['commit_ids']]

    def _normalize_entity_name(self, entity):
        """实体名称标准化"""
        if not entity:
            return None
        
        # 基础清理
        normalized = entity.strip()
        
        # 移除特殊字符
        normalized = re.sub(r'[^\w\s-]', '', normalized)
        
        # 统一空格
        normalized = ' '.join(normalized.split())
        
        return normalized if normalized else None

    @FusionCache.cached_operation('fusion')
    async def _process_single_entity_fusion(self, entity, linked_entities, feature_id=None, commit_ids=None):
        """处理单个实体的融合"""
        # 1. 启发式规则过滤候选项
        candidates = await self._find_fusion_candidates(entity, linked_entities)
        
        # 2. LLM验证
        verified_matches = []
        for candidate in candidates:
            verification = await self._verify_fusion_pair(entity, candidate)
            if verification['decision']:
                verified_matches.append({
                    'entity': candidate,
                    'reason': verification['reason']
                })
                
        if verified_matches:
            # 选择最佳匹配
            best_match = self._select_best_match(verified_matches)
            
            # 查找或创建融合组
            existing_group = await self.db_handler.find_fusion_group(best_match['entity'])
            
            if existing_group:
                return self._merge_fusion_groups(existing_group, [entity])
            else:
                return {
                    'original': best_match['entity'],
                    'variations': [entity],
                    'canonical_form': self._select_canonical_form([best_match['entity'], entity]),
                    'fusion_reason': best_match['reason']
                }
        
        return None

    async def _verify_fusion_pair(self, entity1, entity2):
        """使用LLM验证两个实体是否可以融合"""
        prompt = f"""As a Linux kernel expert, determine if the following two terms refer to the exact same concept in the Linux kernel context.

Term 1: {entity1}
Term 2: {entity2}

Consider:
1. They must refer to exactly the same concept
2. One might be an abbreviation or alternative representation of the other
3. They must be used interchangeably in Linux kernel documentation

Please respond in the following format:
Decision: [YES/NO]
Reason: [Your reasoning]
"""
        
        try:
            response = await self._get_llm_response(prompt)
            
            # 解析响应
            lines = response.strip().split('\n')
            decision = lines[0].split(':')[1].strip().upper() == 'YES'
            reason = lines[1].split(':')[1].strip()
            
            return {
                'decision': decision,
                'reason': reason
            }
        except Exception as e:
            self.logger.error(f"LLM verification failed: {str(e)}")
            return {'decision': False, 'reason': 'Verification failed'}

    def _select_best_match(self, verified_matches):
        """从验证通过的匹配中选择最佳匹配"""
        # 可以基于以下因素选择：
        # 1. 是否来自官方文档
        # 2. 字符串相似度
        # 3. 验证的置信度
        return verified_matches[0]  # 目前简单返回第一个匹配

    def _evaluate_fusion_results(self, fusion_groups):
        """评估融合结果"""
        total_entities = sum(len(group['variations']) + 1 for group in fusion_groups)
        total_groups = len(fusion_groups)
        
        return {
            'total_entities': total_entities,
            'total_groups': total_groups,
            'average_group_size': total_entities / total_groups if total_groups > 0 else 0,
            'fusion_rate': (total_entities - total_groups) / total_entities if total_entities > 0 else 0
        }

    # async def _find_fusion_candidates(self, entity, fusion_pool):
    #     """查找所有可能的融合候选项"""
    #     candidates = set()
        
    #     # 启发式规则匹配
    #     rule_candidates = self._apply_fusion_rules(entity, fusion_pool)
    #     candidates.update(rule_candidates)
        
    #     # # 查询数据库中的同义词
    #     # db_synonyms = await self.db_handler.get_known_synonyms(entity)
    #     # candidates.update(db_synonyms)
        
    #     # # 查询历史融合记录
    #     # historical_synonyms = await self.db_handler.get_historical_fusions(entity)
    #     # candidates.update(historical_synonyms)
        
        # return list(candidates - {entity})

    def _apply_fusion_rules(self, entity, context,fusion_pool):
        """应用启发式规则进行匹配"""
        candidates = set()
        
        # 1. 大小写变体
        lower_entity = entity.lower()
        for other in fusion_pool:
            if other != entity and other.lower() == lower_entity:
                candidates.add(other)
        
        # 2. 常见缩写模式
        if '(' in entity:
            main_part = entity.split('(')[0].strip()
            abbrev = entity.split('(')[1].rstrip(')').strip()
            for other in fusion_pool:
                if other == main_part or other == abbrev:
                    candidates.add(other)
        
        # 3. 驼峰命名和下划线分隔
        words = self._split_identifier(entity)
        if len(words) > 1:
            acronym = ''.join(word[0].upper() for word in words)
            for other in fusion_pool:
                if other == acronym:
                    candidates.add(other)
        
        return candidates

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

    async def _get_llm_response(self, prompt: str) -> str:
        """获取LLM的响应"""
        try:
            # 创建 LLM 实例
            llm = deepseek()
            # 调用 LLM 获取响应
            response = llm.get_response(prompt)
            
            if not response:
                raise ValueError("Empty response received from LLM")
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error getting LLM response: {str(e)}")
            raise  # 重新抛出异常，让调用方处理

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

    async def _get_entity_context(self, entity):
        """获取实体的上下文信息，用于辅助链接
        
        可以从数据库中获取该实体相关的描述信息，或者其出现的代码上下文
        
        Args:
            entity (str): 实体名称
            
        Returns:
            str: 实体的上下文信息
        """
        try:
            # 从数据库获取实体相关信息
            context = await self.db_handler.get_entity_context(entity)
            return context if context else ""
        except Exception as e:
            self.logger.warning(f"Failed to get context for entity {entity}: {str(e)}")
            return ""

    @FusionCache.cached_operation('reference')
    async def _find_entity_reference(self, entity, feature_id=None, commit_ids=None):
        """查找实体的引用源（官方文档或代码）
        
        Args:
            entity (str): 要查找的实体名称
            feature_id (str, optional): 特征ID
            commit_ids (list, optional): 提交ID列表
            
        Returns:
            dict: 包含实体引用信息的字典，如果未找到则返回 {'entity': entity, 'references': [], 'found': False}
        """
        try:
            # 并行执行 Bootlin 和 Kernel Docs 搜索
            bootlin_result, kernel_docs_result = await asyncio.gather(
                self._search_bootlin(entity),
                self._search_kernel_docs(entity)
            )
            
            # 收集所有有效的结果
            references = []
            if bootlin_result:
                references.append(bootlin_result)
            if kernel_docs_result:
                references.append(kernel_docs_result)
            
            # 无论是否找到结果都返回统一格式的字典
            return {
                'entity': entity,
                'references': references,
                'found': bool(references)  # 添加found标志来表示是否找到引用
            }
            
        except Exception as e:
            self.logger.error(f"Error finding reference for entity {entity}: {str(e)}")
            # 发生错误时也返回统一格式的结果
            return {
                'entity': entity,
                'references': [],
                'found': False,
                'error': str(e)
            }

    async def _search_bootlin(self, entity):
        """异步搜索Bootlin并返回结构化结果"""
        # 去除标识符末尾的括号
        if entity.endswith('()'):
            entity = entity[:-2]
        base_url = 'https://elixir.bootlin.com/linux/v6.12.6/A/ident/'
        url = f"{base_url}{entity}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        
        result = None
        
        if response.status_code == 200:
            print(f'在 Bootlin 找到与 "{entity}" 相关的结果。')
            result["reference_type"]= "code",
            result["reference_source"]= "bootlin",
            result["references"].append({
                "entity": entity,
                "references": [{
                    "url": url,
                    "title": f"Bootlin search result for {entity}"
                }]
            })
            result = {
                    'entity': entity,
                    'reference_type': 'code',
                    'reference_source': 'bootlin',
                    'references': [{
                        "url": url,
                        "title": f"Bootlin search result for {entity}"
                    }]
            }
        else:
            print(f'Bootlin 请求失败，状态码: {response.status_code}')
        return result

    async def _search_kernel_docs(self, entity):
        """搜索 Kernel Docs 文档引用
        
        Args:
            entity (str): 要搜索的实体名称
            
        Returns:
            dict: 包含引用信息的字典，如果未找到则返回None
        """
        base_url = 'https://docs.kernel.org/search.html?q='
        
        # 配置 Chrome 选项
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_argument('--silent')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

        driver = None
        try:
            self.logger.info(f"开始搜索 {entity}...")
            driver = webdriver.Chrome(options=chrome_options)
            url = f"{base_url}{entity}"
            driver.get(url)

            # 设置等待时间
            wait = WebDriverWait(driver, 5)

            try:
                # 等待搜索结果加载
                search_summary = wait.until(
                    EC.presence_of_element_located((By.CLASS_NAME, "search-summary"))
                ).text

                if "did not match any documents" in search_summary:
                    self.logger.info(f'在 Kernel Docs 没有找到与 "{entity}" 相关的结果。')
                    return None

                references = []
                links = driver.find_elements(By.TAG_NAME, "a")
                
                for link in links:
                    try:
                        result_url = link.get_attribute('href')
                        if not result_url or not result_url.startswith('http'):
                            continue
                        
                        # 获取链接页面的内容
                        async with aiohttp.ClientSession() as session:
                            async with session.get(result_url) as response:
                                if response.status == 200:
                                    content = await response.text()
                                    if entity.lower() in content.lower():
                                        references.append({
                                            'url': result_url,
                                            'title': link.text
                                        })
                                        self.logger.info(f'在 Kernel Docs 找到相关内容: {result_url}')
                    except Exception as e:
                        self.logger.warning(f"处理链接时出错: {str(e)}")
                        continue

                if references:
                    return {
                        'entity': entity,
                        'reference_type': 'documentation',
                        'reference_source': 'kernel_docs',
                        'references': references
                    }
                else:
                    self.logger.info(f'在 Kernel Docs 没有找到与 "{entity}" 相关的内容。')
                    return None

            except TimeoutException:
                self.logger.warning(f'在 Kernel Docs 搜索超时: "{entity}"')
                return None

        except WebDriverException as e:
            self.logger.error(f"WebDriver错误: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"搜索过程中发生错误: {str(e)}")
            return None
        
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    def _find_candidates_by_rules(self, entity, candidates_pool):
        """使用启发式规则查找可能的融合候选项"""
        matches = set()
        
        # 1. 大小写变体匹配
        entity_lower = entity.lower()
        for candidate in candidates_pool:
            if candidate.lower() == entity_lower:
                matches.add(candidate)
        
        # 2. 缩写匹配
        # 2.1 处理括号内显式标注的缩写
        if '(' in entity:
            main_part = entity.split('(')[0].strip()
            abbrev = entity.split('(')[1].rstrip(')').strip()
            for candidate in candidates_pool:
                if candidate == main_part or candidate == abbrev:
                    matches.add(candidate)
        
        # 2.2 处理首字母缩写
        words = self._split_identifier(entity)
        if len(words) > 1:
            # 生成首字母缩写（全大写）
            acronym = ''.join(word[0].upper() for word in words)
            # 生成首字母缩写（保持原有大小写）
            camel_acronym = ''.join(word[0] for word in words)
            
            for candidate in candidates_pool:
                if candidate in (acronym, camel_acronym):
                    matches.add(candidate)
                # 反向匹配：检查当前实体是否是候选项的缩写
                candidate_words = self._split_identifier(candidate)
                if len(candidate_words) > 1:
                    candidate_acronym = ''.join(word[0].upper() for word in candidate_words)
                    if entity in (candidate_acronym, candidate_acronym.lower()):
                        matches.add(candidate)
        
        return list(matches)

    async def _verify_fusion_pair_with_context(self, entity1, entity2, contexts1, contexts2, reference):
        """使用LLM验证两个实体是否可以融合，考虑上下文和引用源
        
        Args:
            entity1 (str): 第一个实体
            entity2 (str): 第二个实体
            contexts1 (list): 第一个实体的上下文列表
            contexts2 (list): 第二个实体的上下文列表
            reference (dict): 引用源信息
            
        Returns:
            dict: 包含决策和原因的字典
        """
        # 准备上下文信息
        contexts_str = self._prepare_context_string(entity1, entity2, contexts1, contexts2, reference)
        
        prompt = self._create_fusion_verification_prompt(entity1, entity2, contexts_str)
        
        try:
            response = await self._get_llm_response(prompt)
            return self._parse_llm_verification_response(response)
        except Exception as e:
            self.logger.error(f"LLM verification failed: {str(e)}")
            return {'decision': False, 'reason': f'Verification failed: {str(e)}'}

    def _prepare_context_string(self, entity1, entity2, contexts1, contexts2, reference):
        """准备用于LLM验证的上下文字符串"""
        context_parts = []
        
        # # 添加实体1的上下文
        # if contexts1:
        #     context_parts.append(f"Context for {entity1}:")
        #     context_parts.extend(f"- {ctx.get('entity', '')}" for ctx in contexts1)
        
        # # 添加实体2的上下文
        # if contexts2:
        #     context_parts.append(f"\nContext for {entity2}:")
        #     context_parts.extend(f"- {ctx.get('entity', '')}" for ctx in contexts2)
        
        # 添加引用信息
        ref_info = "No official reference available"
        if reference and reference.get('references'):
            ref_info = str(reference['references'][0])
        context_parts.append(f"\nReference Information:\n{ref_info}")
        
        return "\n".join(context_parts)

    def _create_fusion_verification_prompt(self, entity1, entity2, contexts_str):
        """创建用于实体融合验证的提示"""
        return f"""As a Linux kernel expert, determine if the following two terms refer to the exact same concept in the Linux kernel context.

Term 1: {entity1}
Term 2: {entity2}

{contexts_str}

Consider:
1. They must refer to exactly the same concept
2. One might be an abbreviation or alternative representation of the other
3. They must be used interchangeably in Linux kernel documentation
4. Their usage contexts should be consistent
5. The official reference should support their equivalence

Please respond in the following format:
Decision: [YES/NO]
Reason: [Your reasoning]
"""

    def _parse_llm_verification_response(self, response):
        """解析LLM验证响应
        
        Args:
            response (str): LLM的原始响应
            
        Returns:
            dict: 包含决策和原因的字典
        """
        if not response:
            return {'decision': False, 'reason': 'Empty response from LLM'}
        
        response_lines = [line.strip() for line in response.split('\n') if line.strip()]
        
        decision_line = next((line for line in response_lines if line.lower().startswith('decision:')), None)
        reason_line = next((line for line in response_lines if line.lower().startswith('reason:')), None)
        
        if not decision_line or not reason_line:
            return {
                'decision': False,
                'reason': f'Invalid response format. Response: {response}'
            }
        
        decision = 'yes' in decision_line.lower().split(':', 1)[1].strip().lower()
        reason = reason_line.split(':', 1)[1].strip()
        
        return {
            'decision': decision,
            'reason': reason
        }

    async def _get_fusion_candidates(self, entity_name, entity_groups, processed_entities, contexts):
        """获取实体的融合候选项"""
        fusion_candidates = []
        
        # 首先使用现有的 _find_fusion_candidates 方法获取初步候选项
        initial_candidates = self._apply_fusion_rules(entity_name,contexts, entity_groups)
        
        # 对初步候选项进行进一步验证
        for other_name in initial_candidates:
            # 跳过已处理的实体
            if other_name in processed_entities:
                continue
            
            # 获取候选项的上下文和引用
            other_contexts = entity_groups.get(other_name, [])
            other_reference = entity_groups.get(other_name)
            
            # 使用LLM验证融合可能性
            verification = await self._verify_entities_fusion(
                entity_name, other_name, contexts, other_contexts,
                entity_groups[entity_name], other_reference
            )
            
            if verification['decision']:
                fusion_candidates.append({
                    'entity': other_name,
                    'contexts': other_contexts,
                    'reference': other_reference,
                    'reason': verification['reason']
                })
        
        return fusion_candidates

    def _create_fusion_group(self, entity_name, fusion_candidates, contexts, reference):
        """创建融合组"""
        return {
            'original': entity_name,
            'variations': [c['entity'] for c in fusion_candidates],
            'canonical_form': entity_name,
            'contexts': contexts + [ctx for c in fusion_candidates for ctx in c['contexts']],
            'reference': reference,
            'fusion_reason': 'Merged based on reference and context verification'
        }

    def _update_processed_entities(self, processed_entities, entity_name, fusion_candidates):
        """更新已处理的实体集合"""
        processed_entities.add(entity_name)
        processed_entities.update(c['entity'] for c in fusion_candidates)

    async def _verify_entities_fusion(self, entity1, entity2, contexts1, contexts2, ref1, ref2):
        """验证两个实体是否可以融合"""
        verification = await self._verify_fusion_pair_with_context(
            entity1,
            entity2,
            contexts1,
            contexts2,
            {
                'entity1_reference': ref1,
                'entity2_reference': ref2
            }
        )
        return verification

    def _create_entity_key(self, entity_name, feature_id, commit_ids):
        """创建实体的复合键
        
        Args:
            entity_name (str): 实体名称
            feature_id (str): 特征ID
            commit_ids (list): 提交ID列表
            
        Returns:
            str: 由实体名称、特征ID和提交ID组成的复合键
        """
        # 确保commit_ids是有序的
        commit_ids_str = ','.join(sorted(commit_ids)) if commit_ids else ''
        feature_id_str = str(feature_id) if feature_id else ''
        
        return f"{entity_name}_{feature_id_str}_{commit_ids_str}"

    def _evaluate_reference_accuracy(self, entities):
        """评估实体引用的准确性，分别评估代码引用和文档引用
        
        Args:
            entities (dict): 包含实体及其引用信息的字典
        
        Returns:
            dict: 包含代码和文档引用评估指标的字典
        """
        try:
            import pandas as pd
            
            # 读取基准数据集
            benchmark_df = pd.read_excel('data/entity_fusion_benchmark_0108.xlsx')
            
            # 初始化计数器 - 代码引用
            code_metrics = {
                'total_entities': 0,
                'total_with_refs': 0,
                'system_found_refs': 0,
                'correct_found': 0
            }
            
            # 初始化计数器 - 文档引用
            doc_metrics = {
                'total_entities': 0,
                'total_with_refs': 0,
                'system_found_refs': 0,
                'correct_found': 0
            }
            
            # 遍历实体
            for entity_key, entity_data in entities.items():
                entity_name = entity_data['entity']
                code_metrics['total_entities'] += 1
                doc_metrics['total_entities'] += 1
                
                # 在基准数据集中查找对应实体
                benchmark_row = benchmark_df[benchmark_df['original_mention'] == entity_name]
                if benchmark_row.empty:
                    continue
                
                # 获取系统找到的引用
                references = entity_data.get('references', [])
                system_code_refs = []
                system_doc_refs = []
                
                # 分类系统找到的引用
                system_code_refs = []
                system_doc_refs = []
                
                # 直接获取references属性的值作为引用列表
                ref_list = references.get('references', [])
                for ref in ref_list:
                    if ref.get('reference_type') == 'code':
                        system_code_refs.append(ref)
                    elif ref.get('reference_type') == 'documentation':
                        system_doc_refs.append(ref)
                
                # 评估代码引用
                has_code_ref = not pd.isna(benchmark_row['reference(code)'].iloc[0])
                if has_code_ref:
                    code_metrics['total_with_refs'] += 1
                if system_code_refs:
                    code_metrics['system_found_refs'] += 1
                    if has_code_ref:
                        code_metrics['correct_found'] += 1
                
                # 评估文档引用
                has_doc_ref = not pd.isna(benchmark_row['reference(document)'].iloc[0])
                if has_doc_ref:
                    doc_metrics['total_with_refs'] += 1
                if system_doc_refs:
                    doc_metrics['system_found_refs'] += 1
                    if has_doc_ref:
                        doc_metrics['correct_found'] += 1
            
            # 计算代码引用指标
            code_metrics.update(self._calculate_metrics(
                code_metrics['correct_found'],
                code_metrics['system_found_refs'],
                code_metrics['total_with_refs']
            ))
            
            # 计算文档引用指标
            doc_metrics.update(self._calculate_metrics(
                doc_metrics['correct_found'],
                doc_metrics['system_found_refs'],
                doc_metrics['total_with_refs']
            ))
            
            # 记录评估结果
            self._log_evaluation_results(code_metrics, doc_metrics)
            
            return {
                'code_references': code_metrics,
                'doc_references': doc_metrics
            }
            
        except Exception as e:
            self.logger.error(f"Error evaluating reference accuracy: {str(e)}")
            self.logger.error(f"First entity data sample: {next(iter(entities.items())) if entities else 'No entities'}")
            return {
                'code_references': {'error': str(e)},
                'doc_references': {'error': str(e)}
            }

    def _calculate_metrics(self, correct_found, system_found, total_with_refs):
        """计算评估指标
        
        Args:
            correct_found (int): 正确找到的引用数量
            system_found (int): 系统找到的引用数量
            total_with_refs (int): 基准数据集中有引用的实体数量
        
        Returns:
            dict: 包含precision, recall和f1_score的字典
        """
        precision = correct_found / system_found if system_found > 0 else 0
        recall = correct_found / total_with_refs if total_with_refs > 0 else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            'precision': precision,
            'recall': recall,
            'f1_score': f1_score
        }

    def _log_evaluation_results(self, code_metrics, doc_metrics):
        """记录评估结果
        
        Args:
            code_metrics (dict): 代码引用的评估指标
            doc_metrics (dict): 文档引用的评估指标
        """
        metrics_table = f"""
Reference Evaluation Metrics:
┌────────────────────┬───────────────┬───────────────┐
│ Metric            │ Code Refs     │ Doc Refs      │
├────────────────────┼───────────────┼───────────────┤
│ Precision         │ {code_metrics['precision']:.2%} │ {doc_metrics['precision']:.2%} │
│ Recall            │ {code_metrics['recall']:.2%}   │ {doc_metrics['recall']:.2%}   │
│ F1 Score          │ {code_metrics['f1_score']:.2%} │ {doc_metrics['f1_score']:.2%} │
├────────────────────┼───────────────┼───────────────┤
│ Total Entities    │ {code_metrics['total_entities']:>11} │ {doc_metrics['total_entities']:>11} │
│ With References   │ {code_metrics['total_with_refs']:>11} │ {doc_metrics['total_with_refs']:>11} │
│ System Found      │ {code_metrics['system_found_refs']:>11} │ {doc_metrics['system_found_refs']:>11} │
│ Correctly Found   │ {code_metrics['correct_found']:>11} │ {doc_metrics['correct_found']:>11} │
└────────────────────┴───────────────┴───────────────┘"""
        
        self.logger.info(metrics_table)