from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from utils.logger import setup_logger
from utils.deepseek import deepseek
from utils.fusion_cache import FusionCache
import requests
import pandas as pd
import asyncio
import re
import aiohttp
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

class EntityFusion:
    def __init__(self, config):
        self.logger = setup_logger('entity_fusion', file_output=True)
        self.config = config
        self.fusion_cache = FusionCache()
        self.llm = deepseek()
        

    async def process_fusion(self, new_entities, feature_ids=None, commit_ids_list=None):
        """处理实体融合的主流程
        
        Args:
            new_entities (list): 需要进行融合的新实体列表
            feature_ids (list, optional): 与实体一一对应的特征ID列表
            commit_ids_list (list, optional): 与实体一一对应的提交ID列表的列表
        Returns:
            dict: 包含融合结果的字典
        """
        # 1. 预处理 - 标准化和保留上下文信息
        processed_entities = self._preprocess_entities(new_entities, feature_ids, commit_ids_list)
        
        # 2. 分离有引用源和无引用源的实体
        entities_with_refs = {}
        entities_without_refs = {}
        entities = {}

        for item in processed_entities:
            entity_name = item['entity']
            entity_key = self._create_entity_key(
                entity_name,
                item['feature_id'],
                item['commit_ids']
            )

            reference = await self._find_entity_reference(
                entity_name,
                item['feature_id'],
                item['commit_ids'],
                item['candidates']
            )

            if reference and reference['found']:
                if entity_name not in entities_with_refs:
                    entities_with_refs[entity_name] = {
                        'keys': set(),
                        'items': [],
                        'references': []
                    }
                entities_with_refs[entity_name]['keys'].add(entity_key)
                entities_with_refs[entity_name]['items'].append(item)
                entities_with_refs[entity_name]['references'].append(reference)
            else:
                if entity_name not in entities_without_refs:
                    entities_without_refs[entity_name] = {
                        'keys': set(),
                        'items': [],
                        'references': []
                    }
                entities_without_refs[entity_name]['keys'].add(entity_key)
                entities_without_refs[entity_name]['items'].append(item)
                if reference:
                    entities_without_refs[entity_name]['references'].append(reference)
            
            item['references'] = reference
            entities[entity_key] = item

        # 3. 处理有引用源的实体
        fusion_groups = []
        processed_entity_keys = set()

        for entity_name, entity_data in entities_with_refs.items():
            if entity_data['keys'].issubset(processed_entity_keys):
                continue
            
            fusion_candidates = await self._get_fusion_candidates(
                entity_name,
                entities_with_refs,
                processed_entity_keys,
                entity_data['items']
            )
            
            if fusion_candidates:
                group = self._create_fusion_group(
                    entity_name,
                    fusion_candidates,
                    entity_data['items'],
                    entity_data['references']
                )
                fusion_groups.append(group)
                self._update_processed_entities(processed_entity_keys, entity_name, fusion_candidates)
            else:
                # 如果没有找到融合候选项，创建一个单独的融合组
                group = {
                    'original': entity_name,
                    'variations': [],
                    'canonical_form': entity_name,
                    'contexts': entity_data['items'],
                    'reference': entity_data['references'],
                    'fusion_reason': 'No fusion candidates, standalone group'
                }
                fusion_groups.append(group)
                self._update_processed_entities(processed_entity_keys, entity_name, [])

        # 4. 计算统计信息
        stats = self._evaluate_fusion_results(fusion_groups)
        
        return fusion_groups


    def _preprocess_entities(self, entities, feature_ids=None, commit_ids_list=None):
        """预处理实体，但不进行上下文去重
        - 只进行基础的标准化和清洗
        - 保留所有上下文信息供后续融合使用
        """
        processed = []
        
        for i, entity in enumerate(entities):
            # TODO基于规则生成一些变体
            # normalized = self._normalize_entity_name(entity)
            candidates = self._generate_candidates(entity)
            # if not normalized:
            #     continue
            
            entity_info = {
                'entity': entity,
                'candidates': candidates,
                'feature_id': feature_ids[i] if feature_ids else None,
                'commit_ids': commit_ids_list[i] if isinstance(commit_ids_list[i], list) else [commit_ids_list[i]] if commit_ids_list else None
            }
            processed.append(entity_info)
                
        return processed

    # def _normalize_entity_name(self, entity):
    #     
    #     if not entity:
    #         return None
        
    #     # 基础清理
    #     normalized = entity.strip()
        
    #     # 移除特殊字符
    #     normalized = re.sub(r'[^\w\s-]', '', normalized)
        
    #     # 统一空格
    #     normalized = ' '.join(normalized.split())
        
    #     return normalized if normalized else None

    def _generate_candidates(self, entity):
        """生成实体的候选变体
        
        结合规则和大模型方式生成变体：
        1. 使用规则处理基本的命名风格转换
        2. 使用大模型处理复杂的缩写形式
        """
        candidates = set([entity])  
        
        # 1. 使用规则处理基本命名风格，暂时不使用，因为规则生成的变体可能导致搜索不够准确
        # candidates.update(self._generate_naming_variants(entity))
        
        # 2. 使用大模型处理复杂缩写
        abbreviation_variants = self._generate_abbreviation_variants(entity)
        candidates.update(abbreviation_variants)
        
        # 移除无效候选项
        candidates.discard('')
        candidates.discard(None)
        
        return list(candidates)

    # 生成基本的命名风格变体
    def _generate_naming_variants(self, entity):
        """使用规则生成基本的命名风格变体
        """
        variants = set()
        
        # 1. 空格和下划线转换
        if ' ' in entity:
            variants.add(entity.replace(' ', '_'))
        if '_' in entity:
            variants.add(entity.replace('_', ' '))
        
        # 2. 驼峰命名处理
        words = self._split_identifier(entity)
        if len(words) > 1:
            # 驼峰命名
            variants.add(words[0].lower() + ''.join(w.capitalize() for w in words[1:]))
            # 帕斯卡命名
            variants.add(''.join(w.capitalize() for w in words))
            # 全小写下划线
            variants.add('_'.join(w.lower() for w in words))
            # 全大写下划线
            variants.add('_'.join(w.upper() for w in words))
            # 首字母缩写（大写）
            variants.add(''.join(w[0].upper() for w in words))
            # 首字母缩写（小写）
            variants.add(''.join(w[0].lower() for w in words))
        
        return variants

    def _generate_abbreviation_variants(self, entity):
        """使用大模型生成复杂的缩写变体
        """
        # 如果实体长度小于3，不处理缩写
        if len(entity) < 3:
            return []
        
        prompt = f"""As a Linux kernel expert, if "{entity}" is a common term in Linux kernel:
1. If it's a full word, provide its common abbreviation.
2. If it's an abbreviation, provide its full word.
3. Only respond if you're highly confident.

Format: Return each variation on a new line, prefixed with 'Variant: '. If unsure, return 'Variant: None'.
Example for "memory":
Variant: mem
Variant: mem

Example for "mem":
Variant: memory

Example for "unknown_term":
Variant: None
"""

        try:
            response = self._get_llm_response(prompt)
            if not response or response.isspace():
                return []
            
            # 处理响应
            variants = self._parse_and_normalize_response(response)
            
            return variants
            
        except Exception as e:
            self.logger.warning(f"Error generating abbreviation variants for {entity}: {str(e)}")
            return []

    def _parse_and_normalize_response(self, response):
        """解析和规范化大模型的响应"""
        # 去除多余的空格和空行
        response = response.strip()
        
        # 分割响应为变体列表
        variants = [line.split('Variant: ')[1].strip() for line in response.splitlines() if line.startswith('Variant: ') and line.split('Variant: ')[1].strip() != 'None']
        
        # 进一步规范化变体
        normalized_variants = self._normalize_variants(variants)
        
        return normalized_variants

    def _normalize_variants(self, variants):
        """规范化变体列表"""
        normalized = set()
        for variant in variants:
            # 例如：将所有变体转换为小写，去除重复项
            normalized.add(variant.lower())
        return list(normalized)

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

        # TODO memory 缩写成 mem. 需要一个规则来处理：
        
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

    def _get_llm_response(self, prompt: str) -> str:
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
    async def _find_entity_reference(self, entity, feature_id=None, commit_ids=None, candidates=None):
        """查找实体的引用源（官方文档或代码）
        
        Args:
            entity (str): 主要实体名称
            candidates (list): 候选实体名称列表，包含主实体及其变体
            feature_id (str, optional): 特征ID
            commit_ids (list, optional): 提交ID列表
            
        Returns:
            dict: 包含实体引用信息的字典
        """
        try:
            # 对所有候选项并行执行搜索
            search_tasks = []
            for candidate in candidates:
                search_tasks.extend([
                    self._search_bootlin(candidate),
                    self._search_kernel_docs(candidate)
                ])
            
            # 并行执行所有搜索任务
            all_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            # 过滤和整理结果
            valid_references = []
            for result in all_results:
                if isinstance(result, Exception):
                    continue
                if result:  # 如果结果有效
                    valid_references.append(result)
            
            # 返回统一格式的结果
            return {
                'entity': entity,
                'references': valid_references,
                'found': bool(valid_references)
            }
            
        except Exception as e:
            self.logger.error(f"Error finding reference for entity {entity}: {str(e)}")
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