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
from utils.name_handler import NameHandler
from selenium.common.exceptions import TimeoutException, WebDriverException
import concurrent.futures
from functools import partial

class EntityFusion:
    def __init__(self, config):
        self.logger = setup_logger('entity_fusion', file_output=True)
        self.config = config
        self.fusion_cache = FusionCache()
        self.llm = deepseek()

    async def process_fusion(self, new_entities):
        """处理实体融合的主流程

        Args:
            new_entities (list): 需要进行融合的新实体列表
        Returns:
            dict: 包含融合结果的字典
        """
        # 1. 预处理 - 标准化和保留上下文信息
        processed_entities = await self._preprocess_entities(new_entities)

        # 2. 分离有引用源和无引用源的实体
        entities_with_refs = {}
        entities_without_refs = {}
        entities = {}

        for item in processed_entities:
            entity_name = item['entity']
            entity_key = self._create_entity_key(entity_name)

            reference = await self._find_entity_reference(
                entity_name,
                candidates=item['candidates']
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

            self.logger.info(f"Processing entity: {entity_name}")
            self.logger.info(f"Processed entities so far: {processed_entity_keys}")

            fusion_candidates = await self._get_fusion_candidates(
                entity_name,
                entities_with_refs,
                processed_entity_keys,
                entity_data['items']
            )
            if fusion_candidates is not None:
                group = self._create_fusion_group(
                    entity_name,
                    fusion_candidates,
                    entity_data['items'],
                    entity_data['references']
                )
                fusion_groups.append(group)
                self._update_processed_entities(processed_entity_keys, entity_name, fusion_candidates)
            else:
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
        self._evaluate_reference_accuracy(entities_with_refs)

        return fusion_groups

    async def _preprocess_entities(self, entities):
        """预处理实体，不使用 feature_ids 和 commit_ids_list"""
        processed = []

        for entity in entities:
            candidates = await self._generate_candidates(entity)
            entity_info = {
                'entity': entity,
                'candidates': candidates
            }
            processed.append(entity_info)

        return processed

    @FusionCache.cached_operation('candidates')
    async def _generate_candidates(self, entity):
        """生成实体的候选变体"""
        candidates = set([entity])

        candidates.update(self._generate_naming_variants(entity))

        abbreviation_variants = await self._generate_abbreviation_variants(entity)
        candidates.update(abbreviation_variants)

        candidates.discard('')
        candidates.discard(None)

        return list(candidates)

    def _generate_naming_variants(self, entity):
        """使用规则生成基本的命名风格变体"""
        if not entity or not isinstance(entity, str):
            return set()

        variants = {entity}

        entity = ' '.join(entity.split())

        words = self._split_identifier(entity)
        if not words:
            return variants

        if len(words) > 1:
            underscore = '_'.join(words)
            variants.add(underscore)

            space = ' '.join(words)
            variants.add(space)

            camel = words[0].lower() + ''.join(w.capitalize() for w in words[1:])
            variants.add(camel)

            pascal = ''.join(w.capitalize() for w in words)
            variants.add(pascal)

            lower_underscore = '_'.join(w.lower() for w in words)
            variants.add(lower_underscore)

            upper_underscore = '_'.join(w.upper() for w in words)
            variants.add(upper_underscore)

            if 2 <= len(words) <= 5:
                upper_acronym = ''.join(w[0].upper() for w in words)
                variants.add(upper_acronym)
                lower_acronym = ''.join(w[0].lower() for w in words)
                variants.add(lower_acronym)

        variants = {v for v in variants if v and len(v.strip()) > 0}

        return variants

    async def _generate_abbreviation_variants(self, entity):
        """使用大模型生成复杂的缩写变体"""
        if len(entity) < 3:
            return []

        prompt = f"""As a Linux kernel expert, if "{entity}" is a common term in Linux kernel:
1. If it's a full word, provide its common abbreviation.
2. If it's an abbreviation, provide its full word.
3. Only respond if you're highly confident.

Format: Return each variation on a new line, prefixed with 'Variant: '. If unsure, return 'Variant: None'.
Example for "memory":
Variant: mem

Example for "mem":
Variant: memory

Example for "unknown_term":
Variant: None
"""

        try:
            response = self._get_llm_response(prompt)
            if not response:
                return []

            variants = self._parse_and_normalize_response(response)
            return variants

        except Exception as e:
            self.logger.warning(f"Error generating abbreviation variants for {entity}: {str(e)}")
            return []

    def _parse_and_normalize_response(self, response):
        """解析和规范化大模型的响应"""
        response = response.strip()
        variants = [line.split('Variant: ')[1].strip() for line in response.splitlines() if line.startswith('Variant: ') and line.split('Variant: ')[1].strip() != 'None']
        normalized_variants = self._normalize_variants(variants)
        return normalized_variants

    def _normalize_variants(self, variants):
        """规范化变体列表"""
        normalized = set()
        for variant in variants:
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

    def _apply_fusion_rules(self, entity, context, fusion_pool):
        """应用启发式规则进行匹配"""
        candidates = set()

        lower_entity = entity.lower()
        for other in fusion_pool:
            if other != entity and other.lower() == lower_entity:
                candidates.add(other)

        if '(' in entity:
            main_part = entity.split('(')[0].strip()
            abbrev = entity.split('(')[1].rstrip(')').strip()
            for other in fusion_pool:
                if other == main_part or other == abbrev:
                    candidates.add(other)

        words = self._split_identifier(entity)
        if len(words) > 1:
            acronym = ''.join(word[0].upper() for word in words)
            for other in fusion_pool:
                if other == acronym:
                    candidates.add(other)

        return candidates

    def _split_identifier(self, identifier: str) -> list:
        """将标识符分解为单词列表"""
        parts = identifier.split('_')
        words = []
        for part in parts:
            camel_words = re.findall(r'[A-Z][a-z]*|[a-z]+|[A-Z]{2,}(?=[A-Z][a-z]|\d|\W|$)|\d+', part)
            words.extend(camel_words)
        return words

    def _get_llm_response(self, prompt: str) -> str:
        """获取LLM的响应"""
        try:
            response = self.llm.get_response(prompt)
            if not response:
                raise ValueError("Empty response received from LLM")
            return response
        except Exception as e:
            self.logger.error(f"Error getting LLM response: {str(e)}")
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

    def _select_canonical_form(self, variations: list) -> str:
        """从变体中选择规范形式"""
        if not variations:
            return ""

        sorted_vars = sorted(variations, key=len, reverse=True)
        has_abbrev = any(v.isupper() and len(v) <= 5 for v in variations)

        if has_abbrev:
            for var in sorted_vars:
                if not (var.isupper() and len(var) <= 5):
                    return var

        return sorted_vars[0]

    async def _get_entity_context(self, entity):
        """获取实体的上下文信息，用于辅助链接"""
        try:
            context = await self.db_handler.get_entity_context(entity)
            return context if context else ""
        except Exception as e:
            self.logger.warning(f"Failed to get context for entity {entity}: {str(e)}")
            return ""

    async def _find_entity_reference(self, entity, candidates=None):
        """查找实体的引用源（官方文档或代码）"""
        try:
            search_tasks = []
            for candidate in candidates:
                search_tasks.extend([
                    self._search_bootlin(candidate),
                    self._search_kernel_docs(candidate)
                ])

            all_results = await asyncio.gather(*search_tasks, return_exceptions=True)

            valid_references = []
            for result in all_results:
                if isinstance(result, Exception):
                    continue
                if result:
                    valid_references.append(result)

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
        if entity.endswith('()'):
            entity = entity[:-2]

        base_url = 'https://elixir.bootlin.com/linux/v6.12.6/A/ident/'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36'
        }

        url = f"{base_url}{entity}"
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            print(f'在 Bootlin 找到与 "{entity}" 相关的结果。')
            return {
                'entity': entity,
                'reference_type': 'code',
                'reference_source': 'bootlin',
                'references': [{
                    "url": url,
                    "title": f"Bootlin search result for {entity}"
                }]
            }

        underscored_entity = '_'.join(entity.split())
        if underscored_entity != entity:
            url = f"{base_url}{underscored_entity}"
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                print(f'在 Bootlin 找到与 "{underscored_entity}" 相关的结果。')
                return {
                    'entity': entity,
                    'reference_type': 'code',
                    'reference_source': 'bootlin',
                    'references': [{
                        "url": url,
                        "title": f"Bootlin search result for {underscored_entity}"
                    }]
                }
            else:
                print(f'Bootlin 搜索失败，状态码: {response.status_code}')

        return None

    async def _search_kernel_docs(self, entity):
        """搜索 Kernel Docs 文档引用"""
        base_url = 'https://docs.kernel.org/search.html?q='

        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-setuid-sandbox')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_argument('--silent')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

        driver = None
        try:
            self.logger.info(f"开始搜索 {entity}...")
            driver = webdriver.Chrome(options=chrome_options)
            url = f"{base_url}{entity}"
            driver.get(url)

            wait = WebDriverWait(driver, 6)
            search_summary_element = wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, "search-summary"))
            )
            search_summary = search_summary_element.text
            print("Search Summary:", search_summary)

            if "did not match any documents" in search_summary:
                self.logger.info(f'在 Kernel Docs 没有找到与 "{entity}" 相关的结果。')
                return None

            references = []
            try:
                search_container = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "search"))
                )
                links = search_container.find_elements(By.TAG_NAME, "a")
            except Exception as exc:
                self.logger.warning(f"无法找到 class='search' 下的链接: {exc}. 尝试从整个页面查找链接。")
                links = driver.find_elements(By.TAG_NAME, "a")

            for link in links:
                try:
                    result_url = link.get_attribute('href')
                    if not result_url or not result_url.startswith('http'):
                        continue

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
                                    if len(references) >= 5:
                                        break
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

        entity_lower = entity.lower()
        for candidate in candidates_pool:
            if candidate.lower() == entity_lower:
                matches.add(candidate)

        if '(' in entity:
            main_part = entity.split('(')[0].strip()
            abbrev = entity.split('(')[1].rstrip(')').strip()
            for candidate in candidates_pool:
                if candidate == main_part or candidate == abbrev:
                    matches.add(candidate)

        words = self._split_identifier(entity)
        if len(words) > 1:
            acronym = ''.join(word[0].upper() for word in words)
            for candidate in candidates_pool:
                if candidate in (acronym, acronym.lower()):
                    matches.add(candidate)
                candidate_words = self._split_identifier(candidate)
                if len(candidate_words) > 1:
                    candidate_acronym = ''.join(word[0].upper() for word in candidate_words)
                    if entity in (candidate_acronym, candidate_acronym.lower()):
                        matches.add(candidate)

        return list(matches)

    async def _verify_fusion_pair_with_context(self, entity1, entity2, contexts1, contexts2, reference):
        """使用LLM验证两个实体是否可以融合"""
        contexts_str = self._prepare_context_string(entity1, entity2, contexts1, contexts2, reference)
        prompt = self._create_fusion_verification_prompt(entity1, entity2, contexts_str)

        try:
            response = self._get_llm_response(prompt)
            return self._parse_llm_verification_response(response)
        except Exception as e:
            self.logger.error(f"LLM verification failed: {str(e)}")
            return {'decision': False, 'reason': f'Verification failed: {str(e)}'}

    def _prepare_context_string(self, entity1, entity2, contexts1, contexts2, reference):
        """准备用于LLM验证的上下文字符串"""
        context_parts = []

        if contexts1:
            context_parts.append(f"Context for {entity1}:")
            context_parts.extend(f"- {ctx.get('entity', '')}" for ctx in contexts1)

        if contexts2:
            context_parts.append(f"\nContext for {entity2}:")
            context_parts.extend(f"- {ctx.get('entity', '')}" for ctx in contexts2)

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
        """解析LLM验证响应"""
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

        initial_candidates = self._apply_fusion_rules(entity_name, contexts, entity_groups)

        for other_name in initial_candidates:
            if other_name in processed_entities:
                continue

            other_contexts = entity_groups.get(other_name, [])
            other_reference = entity_groups.get(other_name)

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

    def _create_entity_key(self, entity_name):
        """创建实体的复合键，仅基于实体名称"""
        return entity_name

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
            entity1, entity2, contexts1, contexts2,
            {'entity1_reference': ref1, 'entity2_reference': ref2}
        )
        return verification

    def _evaluate_reference_accuracy(self, entities):
        """评估实体引用的准确性"""
        try:
            code_metrics = {
                'total_entities': 0,
                'total_with_refs': 0,
                'system_found_refs': 0,
                'correct_found': 0
            }
            doc_metrics = {
                'total_entities': 0,
                'total_with_refs': 0,
                'system_found_refs': 0,
                'correct_found': 0
            }

            for entity_key, entity_data in entities.items():
                code_metrics['total_entities'] += 1
                doc_metrics['total_entities'] += 1

                reference_data = entity_data.get('references', [])
                system_code_refs = []
                system_doc_refs = []

                for ref in reference_data:
                    ref_type = ref.get('reference_type')
                    if ref_type == 'code':
                        system_code_refs.append(ref)
                    elif ref_type == 'documentation':
                        system_doc_refs.append(ref)

                if system_code_refs:
                    code_metrics['system_found_refs'] += 1
                if system_doc_refs:
                    doc_metrics['system_found_refs'] += 1

            self._log_evaluation_results(code_metrics, doc_metrics)
            return {
                'code_references': code_metrics,
                'doc_references': doc_metrics
            }

        except Exception as e:
            self.logger.error(f"Error evaluating reference accuracy: {str(e)}")
            return {
                'code_references': {'error': str(e)},
                'doc_references': {'error': str(e)}
            }

    def _calculate_metrics(self, correct_found, system_found, total_with_refs):
        """计算评估指标"""
        precision = correct_found / system_found if system_found > 0 else 0
        recall = correct_found / total_with_refs if total_with_refs > 0 else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        return {
            'precision': precision,
            'recall': recall,
            'f1_score': f1_score
        }

    def _log_evaluation_results(self, code_metrics, doc_metrics):
        """记录评估结果"""
        metrics_table = f"""
Reference Evaluation Metrics:
┌────────────────────┬───────────────┬───────────────┐
│ Metric            │ Code Refs     │ Doc Refs      │
├────────────────────┼───────────────┼───────────────┤
│ Total Entities    │ {code_metrics['total_entities']:>11} │ {doc_metrics['total_entities']:>11} │
│ System Found      │ {code_metrics['system_found_refs']:>11} │ {doc_metrics['system_found_refs']:>11} │
└────────────────────┴───────────────┴───────────────┘"""
        self.logger.info(metrics_table)

def init_driver_with_enhanced_options():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-setuid-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--silent")
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

    driver = webdriver.Chrome(options=chrome_options)
    driver.get("https://www.google.com")
    print("Page title:", driver.title)
    driver.quit()

if __name__ == "__main__":
    init_driver_with_enhanced_options()