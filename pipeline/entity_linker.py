import logging
import requests
from bs4 import BeautifulSoup
import asyncio
import json
from typing import List, Dict, Optional, Tuple, Union
from dataclasses import dataclass
from utils.logger import setup_logger
from utils.deepseek import deepseek
from utils.utils import strip_json
from prompts.link import linkPrompt
import wikipediaapi
import re
import aiohttp
from utils.link_cache import LinkCache
from models.linking import LinkingCandidate
from srctoolkit import Delimiter
import time

class EntityLinker:
    def __init__(self, config):
        self.logger = setup_logger('entity_linker', file_output=True)
        self.config = config
        self.llm = deepseek()
        self.timeout = 3  # 3秒超时
        self.max_retries = 2  # 最多重试2次
        self.wiki = wikipediaapi.Wikipedia(
            language='en',
            extract_format=wikipediaapi.ExtractFormat.HTML,
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0',
        )
        self.link_cache = LinkCache()

    async def link_entity(self, entity):
        """链接单个实体到知识库，返回所有可能的匹配结果"""
        start_time = time.time()
        self.logger.info(f"Processing entity linking for: {entity}")

        # 1. 生成所有可能的搜索词（限制变体数量）
        variations_start = time.time()
        variations = await self._generate_variations(entity)
        filtered_variations = [v for v in variations if len(v) > 2 and v.lower() != 'mm']
        filtered_variations.append(entity)
        filtered_variations = list(dict.fromkeys(filtered_variations))
        self.logger.info(f"Variations generated: {filtered_variations}")
        self.logger.info(f"Variations generation took {time.time() - variations_start:.2f}s")

        # 2. 搜索维基百科
        wiki_search_start = time.time()
        primary_candidates = []
        for term in filtered_variations:
            wiki_results = await self._search_wikipedia(term)
            primary_candidates.extend(wiki_results)

        # 如果 Wikipedia 未找到候选，尝试 Bootlin 搜索
        if not primary_candidates:
            self.logger.info(f"No Wikipedia candidates found for {entity}, attempting Bootlin search")
            bootlin_result = await self._search_bootlin(entity)
            if bootlin_result:
                primary_candidates.append(bootlin_result)

        primary_candidates = self._deduplicate_candidates(primary_candidates)
        self.logger.info(f"Primary search took {time.time() - wiki_search_start:.2f}s")

        # 3. 选择最佳匹配
        best_match_start = time.time()
        primary_match = await self._select_best_match(entity, primary_candidates)
        self.logger.info(f"Best match selection took {time.time() - best_match_start:.2f}s")

        # 整理结果
        matches = []
        if primary_match and primary_match.confidence > 0.5:
            matches.append({
                'linked_entity': primary_match.title,
                'wikipedia_url': primary_match.url,
                'confidence': primary_match.confidence,
                'search_terms': filtered_variations,
                'candidates_count': len(primary_candidates),
                'match_type': 'primary'
            })

        result = {
            'mention': entity,
            'matches': matches,
            'total_candidates_count': len(primary_candidates)
        }

        total_time = time.time() - start_time
        self.logger.info(f"Total entity linking process took {total_time:.2f}s for entity: {entity}")
        return result

    @LinkCache.cached_operation('variations')
    async def _generate_variations(self, mention: str) -> List[str]:
        """生成术语的变体，限制为 Linux 内核相关"""
        prompt = self._create_variation_prompt(mention)
        response = await self._get_llm_response(prompt)
        variations = self._parse_variations_response(response, mention)
        if len(variations) > 5:
            variations = variations[:5]  # 只取前5个变体
        return variations

    def _process_sections(self, page, term, sections, depth=0):
        """递归处理所有层级的章节"""
        candidates = []

        for section in sections:
            if section.title.lower() == term.lower():
                section_path = []
                current = section
                for _ in range(depth + 1):
                    section_path.insert(0, current.title)
                    if not hasattr(current, 'parent'):
                        break
                    current = current.parent

                anchor = '_'.join(
                    title.replace(' ', '_')
                    .replace('(', '.28')
                    .replace(')', '.29')
                    .replace(',', '.2C')
                    for title in section_path
                )

                candidate = LinkingCandidate(
                    mention=term,
                    title=f"{page.title}#{' > '.join(section_path)}",
                    url=f"{page.fullurl}#{anchor}",
                    summary=section.text[:200],
                    confidence=0.0,
                    is_disambiguation=False
                )
                candidates.append(candidate)

            if section.sections:
                candidates.extend(self._process_sections(page, term, section.sections, depth + 1))

        return candidates

    @LinkCache.cached_operation('main')
    async def _get_wikipedia_page_candidates(self, term: str, page=None) -> List[LinkingCandidate]:
        """处理维基百科页面并返回候选项"""
        candidates = []

        section_candidates = await self._find_matching_sections(page, term)
        if section_candidates:
            return section_candidates

        is_match, confidence = await self._check_page_relevance(page.title, page.summary, term)
        if is_match:
            candidate = LinkingCandidate(
                mention=term,
                title=page.title,
                url=page.fullurl,
                summary=page.summary[:200],
                confidence=confidence,
                is_disambiguation=False
            )
            candidates.append(candidate)

        return candidates

    async def _find_matching_sections(self, page, term: str) -> List[LinkingCandidate]:
        """查找匹配的章节并构建带锚点的URL"""
        candidates = []

        def process_section(section, parent_path=[]):
            current_path = parent_path + [section.title]

            if section.title.lower() == term.lower() or term.lower() in section.text.lower()[:200]:
                anchor = '_'.join(
                    title.replace(' ', '_')
                    .replace('(', '.28')
                    .replace(')', '.29')
                    .replace(',', '.2C')
                    for title in current_path
                )

                section_url = f"{page.fullurl}#{anchor}"
                full_title = f"{page.title}#{' > '.join(current_path)}"

                candidate = LinkingCandidate(
                    mention=term,
                    title=full_title,
                    url=section_url,
                    summary=section.text[:200],
                    confidence=0.8 if section.title.lower() == term.lower() else 0.6,
                    is_disambiguation=False
                )
                candidates.append(candidate)

            for subsection in section.sections:
                process_section(subsection, current_path)

        for section in page.sections:
            process_section(section)

        return candidates

    async def _search_wikipedia(self, term: str) -> List[LinkingCandidate]:
        """使用wikipedia-api搜索维基百科，优化消歧义处理"""
        try:
            page = self.wiki.page(term)
            candidates = []

            if not page.exists():
                return []

            if self._is_disambiguation_page(page):
                disambig_candidates = await self._handle_disambiguation_with_relevance(term, page=page)
                filtered_candidates = []
                for candidate in disambig_candidates[:3]:
                    if any(keyword in candidate.title.lower() for keyword in ['memory', 'kernel', 'linux', 'management']):
                        is_match, confidence = await self._check_page_relevance(candidate.title, candidate.summary, term)
                        if is_match:
                            candidate.confidence = confidence
                            filtered_candidates.append(candidate)
                candidates.extend(filtered_candidates)
            else:
                page_candidates = await self._get_wikipedia_page_candidates(term, page=page)
                candidates.extend(page_candidates)

            return candidates

        except Exception as e:
            self.logger.error(f"Wikipedia search failed for term {term}: {e}")
            return []

    async def _search_bootlin(self, entity):
        """搜索 Bootlin 作为备用来源"""
        if entity.endswith('()'):
            entity = entity[:-2]

        base_url = 'https://elixir.bootlin.com/linux/v6.12.6/A/ident/'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36'
        }

        url = f"{base_url}{entity}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        self.logger.info(f'在 Bootlin 找到与 "{entity}" 相关的结果。')
                        return LinkingCandidate(
                            mention=entity,
                            title=f"Bootlin: {entity}",
                            url=url,
                            summary=f"Bootlin search result for {entity}",
                            confidence=0.0,
                            is_disambiguation=False
                        )
                    else:
                        self.logger.info(f'Bootlin 搜索失败，状态码: {response.status}')
                        return None
        except Exception as e:
            self.logger.error(f"Bootlin search failed for {entity}: {e}")
            return None

    def _is_disambiguation_page(self, page) -> bool:
        """检查页面是否为消歧义页面"""
        try:
            disambiguation_categories = [
                'Category:Disambiguation pages',
                'Category:All disambiguation pages',
                'Category:All article disambiguation pages'
            ]

            for category in page.categories:
                if any(dc.lower() in category.lower() for dc in disambiguation_categories):
                    return True

            if 'may refer to:' in page.text.lower():
                return True

            return False

        except Exception as e:
            self.logger.error(f"Failed to check disambiguation for page {page.title}: {e}")
            return False

    @LinkCache.cached_operation('disambig')
    async def _handle_disambiguation_with_relevance(self, term: str, page=None) -> List[LinkingCandidate]:
        """处理消歧义页面并检查相关性"""
        disambig_candidates = self._handle_disambiguation_page(term, page)
        filtered_candidates = []

        for candidate in disambig_candidates:
            is_match, confidence = await self._check_page_relevance(candidate.title, candidate.summary, term)
            if is_match:
                candidate.confidence = confidence
                filtered_candidates.append(candidate)

        return filtered_candidates

    def _handle_disambiguation_page(self, mention, disambig_page) -> List[LinkingCandidate]:
        """处理消歧义页面，提取所有可能的具体页面"""
        candidates = []
        try:
            links = disambig_page.links

            for title in list(links.keys()):
                linked_page = self.wiki.page(title)
                if not linked_page.exists() or self._is_disambiguation_page(linked_page):
                    continue

                candidate = LinkingCandidate(
                    mention=mention,
                    title=linked_page.title,
                    url=linked_page.fullurl,
                    summary=linked_page.summary[:200],
                    confidence=0.0,
                    is_disambiguation=False
                )
                candidates.append(candidate)

            return candidates

        except Exception as e:
            self.logger.error(f"Failed to handle disambiguation page {disambig_page.title}: {e}")
            return []

    async def _check_disambiguation(self, title: str) -> bool:
        """检查页面是否为消歧义页面"""
        try:
            page = self.wiki.page(title)
            return page.is_disambiguation

        except Exception as e:
            self.logger.error(f"Disambiguation check failed for {title}: {e}")
            return False

    async def _select_best_match(self, mention: str, candidates: List[LinkingCandidate]) -> Optional[LinkingCandidate]:
        """使用 LLM 从候选中选择最佳匹配"""
        if not candidates:
            return None

        try:
            prompt = f"""{{
                "task": "Entity Linking and Disambiguation",
                "context": "Given a mention from Linux kernel documentation, select the most appropriate page from the candidates based on the mention alone. Candidates may come from Wikipedia or Bootlin.",
                "mention": "{mention}",
                "candidates": [
                    {self._format_candidates(candidates)}
                ],
                "instructions": "Please analyze each candidate carefully and return a JSON object with:
                    1. 'selected_index': index of the best matching candidate (or -1 if none matches)
                    2. 'confidence': confidence score between 0 and 1
                    3. 'reasoning': brief explanation of your choice"
            }}"""

            response = await self._get_llm_response(prompt)
            if not response:
                return None

            cleaned_response = strip_json(response)
            if not cleaned_response:
                return None

            result = json.loads(cleaned_response)

            if isinstance(result, dict) and 'selected_index' in result:
                if result['selected_index'] >= 0 and result['selected_index'] < len(candidates):
                    selected = candidates[result['selected_index']]
                    selected.confidence = result.get('confidence', 0.0)
                    self.logger.info(f"Selected '{selected.title}' with confidence {selected.confidence}. "
                                     f"Reasoning: {result.get('reasoning', 'No reasoning provided')}")
                    return selected
            return None

        except Exception as e:
            self.logger.error(f"Failed to select best match for {mention}: {e}")
            return None

    def _deduplicate_candidates(self, candidates: List[LinkingCandidate]) -> List[LinkingCandidate]:
        """去除重复的候选"""
        seen = set()
        unique_candidates = []

        for candidate in candidates:
            if candidate.title not in seen:
                seen.add(candidate.title)
                unique_candidates.append(candidate)

        return unique_candidates

    def _create_variation_prompt(self, mention: str) -> str:
        """创建生成变体的提示"""
        return f"""Please generate variations of the following technical term from Linux kernel documentation.
        Return ONLY a JSON array of strings containing Linux kernel related terms that you are CERTAIN about:
        1. The original term (if it is a valid Linux kernel term)
        2. Common abbreviations (ONLY if widely used in Linux kernel documentation)
        3. Full forms (ONLY if it is the official term used in Linux kernel)
        
        Note: 
        - Only include terms that you can verify from official Linux kernel documentation
        - It's better to return fewer but accurate terms than many uncertain ones
        - If you're not confident about a term, do not include it
        - Return empty array if you're not certain about any variations
        Term: "{mention}"
        
        Example response format:
        ["Virtual Memory", "VM", "virtual memory", "virt_mem"]
        """

    def _parse_variations_response(self, response: str, mention: str) -> List[str]:
        """解析 LLM 响应"""
        try:
            cleaned_response = strip_json(response)
            variations = json.loads(cleaned_response)

            if isinstance(variations, list):
                return [v.strip() for v in variations if v and isinstance(v, str)]
            return []

        except Exception as e:
            self.logger.error(f"Failed to parse variations response: {e}")
            return [mention]

    async def _get_llm_response(self, prompt: str) -> str:
        """封装 LLM 调用"""
        try:
            response = self.llm.get_response(prompt)
            return response
        except Exception as e:
            self.logger.error(f"LLM request failed: {e}")
            raise

    def _format_candidates(self, candidates: List[Union[LinkingCandidate, str]]) -> str:
        """格式化候选项为 JSON 字符串"""
        formatted = []
        for i, c in enumerate(candidates):
            if isinstance(c, str):
                formatted.append(f"""{{
                    "index": {i},
                    "title": "{c}"
                }}""")
            else:
                formatted.append(f"""{{
                    "index": {i}, 
                    "title": "{c.title}",
                    "url": "{c.url}",
                    "summary": "{c.summary}",
                    "is_disambiguation": {str(c.is_disambiguation).lower()}
                }}""")
        return ",".join(formatted)

    async def _check_page_relevance(self, title: str, content: str, original_term: str) -> Tuple[bool, float]:
        """使用LLM判断页面是否相关"""
        prompt = f"""Given a term from Linux kernel documentation, analyze if this page appropriately matches the concept as used in the Linux context.

        Original term: {original_term}
        Page:
        Title: {title}
        Content: {content[:500]}

        Consider:
        1. Does this page describe the same concept or a directly relevant concept as used in the Linux context?
        2. While they don't need to be exactly identical, the core concept should match. For example:
           - Good match: "MMU" and "Memory Management Unit" (one is abbreviation of the other)
           - Poor match: "handle_pte_fault" and "Page table" (only indirectly related)
        3. Is this the technical meaning of the term we're looking for?

        Return a JSON object with the following structure:
        {{
            "linux_meaning": "Brief explanation of the term's meaning in Linux context",
            "page_meaning": "Brief explanation of the page's concept",
            "confidence": 0-1,
            "reasoning": "Brief explanation of why they match or don't match",
            "is_match": true/false
        }}
        """

        try:
            response = await self._get_llm_response(prompt)
            cleaned_response = strip_json(response)
            result = json.loads(cleaned_response)

            self.logger.info(f"Relevance analysis for {original_term} -> {title}:\n{json.dumps(result, indent=2)}")

            is_match = result.get('is_match', False)
            confidence = result.get('confidence', 0.0)

            return is_match, confidence

        except Exception as e:
            self.logger.error(f"Failed to check page relevance for {title}: {e}")
            return False, 0.0