import logging
import requests
from bs4 import BeautifulSoup
import asyncio
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from utils.logger import setup_logger
from utils.deepseek import deepseek
from utils.utils import strip_json
from prompts.link import linkPrompt
import wikipediaapi  # 添加新的导入
import re


@dataclass
class LinkingCandidate:
    mention: str
    title: str
    url: str
    summary: str
    confidence: float
    is_disambiguation: bool

class EntityLinker:
    def __init__(self, config):
        self.logger = setup_logger('entity_linker', file_output=True)
        self.config = config
        self.llm = deepseek()
        # 设置请求超时和重试次数
        self.timeout = 3  # 3秒超时
        self.max_retries = 2  # 最多重试2次
        self.wiki = wikipediaapi.Wikipedia(
            language='en',
            extract_format=wikipediaapi.ExtractFormat.HTML,
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0',
            proxies=self.config.WIKIPEDIA_PROXY_URL
        )
     
    async def link_entity(self, entity, context):
        """链接单个实体到知识库，返回所有可能的匹配结果"""
        self.logger.info(f"Processing entity linking for: {entity}")
        
        # 1. 尝试原始实体及其变体匹配
        variations = await self._generate_variations(entity)
        primary_candidates = []
        for term in variations:
            wiki_results = await self._search_wikipedia(term, context)
            primary_candidates.extend(wiki_results)
        
        primary_candidates = self._deduplicate_candidates(primary_candidates)
        self.logger.info(f"for entity {entity} overall linking, got {len(primary_candidates)} page candidates:\n{self._format_candidates(primary_candidates)}")
        primary_match = await self._select_best_match(entity, context, primary_candidates)
        
        
        # 2. 独立尝试n-gram子序列匹配
        ngrams = self._generate_ngrams(entity)
        # 3. 搜索维基百科
        ngram_candidates = []
        for term in ngrams:
            wiki_results = await self._search_wikipedia(term, context)
            ngram_candidates.extend(wiki_results)
        
        ngram_candidates = self._deduplicate_candidates(ngram_candidates)
        self.logger.info(f"for entity {entity} ngram linking, ngrams:\n{ngrams}\ngot {len(ngram_candidates)} page candidates:\n{self._format_candidates(ngram_candidates)}")
        # 4. 使用 LLM 选择 n-grams 最佳匹配
        ngram_match = await self._select_best_match_ngrams(ngrams, context, ngram_candidates)
        
        # 3. 整理所有匹配结果
        matches = []
        
        if primary_match and primary_match.confidence > 0.5:  # 可配置的最低置信度阈值
            matches.append({
                'linked_entity': primary_match.title,
                'wikipedia_url': primary_match.url,
                'confidence': primary_match.confidence,
                'search_terms': variations,
                'candidates_count': len(primary_candidates),
                'match_type': 'primary'
            })
            
        if ngram_match and ngram_match.confidence > 0.5:
            matches.append({
                'linked_entity': ngram_match.title,
                'wikipedia_url': ngram_match.url,
                'confidence': ngram_match.confidence,
                'search_terms': ngrams,
                'candidates_count': len(ngram_candidates),
                'match_type': 'ngram',
                'matched_ngram': ngram_match.mention
            })
        
        return {
            'mention': entity,
            'matches': matches,
            'total_candidates_count': len(primary_candidates) + len(ngram_candidates)
        }
        
    async def _generate_variations(self, mention: str) -> List[str]:
        prompt = self._create_variation_prompt(mention)
        response = await self._get_llm_response(prompt)
        return self._parse_variations_response(response, mention)
            
    def _generate_ngrams(self, text: str, min_n: int = 1, max_n: int = 3) -> List[str]:
        """生成文本的 n-gram 子序列，利用 config 中定义的分隔符"""
        words = re.split(f"[{re.escape(self.config.NGRAM_DELIMITERS)}]+", text)
        ngrams = []
        
        # 生成所有 min_n...max_n-gram 子序列，注意不能和原始文本相同
        for n in range(min_n, max_n + 1):
            for i in range(len(words) - n + 1):
                ngram = " ".join(words[i:i + n])
                if i != 0 or i + n != len(words): # 不是整个文本
                    ngrams.append(ngram)
        
        # 去重，但保留顺序不变
        ngrams = list(dict.fromkeys(ngrams))

        return ngrams
        
    async def _search_wikipedia(self, term: str, context: str = None) -> List[LinkingCandidate]:
        """使用wikipedia-api搜索维基百科，处理消歧义页面"""
        try:
            page = self.wiki.page(term)
            candidates = []
            
            if not page.exists():
                return []
            
            # 通过检查页面内容来判断是否为消歧义页面
            is_disambiguation = self._is_disambiguation_page(page)
                
            if is_disambiguation:
                # 处理消歧义页面
                disambig_candidates = await self._handle_disambiguation_page(page)
                # 对消歧义候选进行相关性过滤
                filtered_candidates = [
                    candidate for candidate in disambig_candidates 
                    if await self._check_page_relevance(candidate.title, candidate.summary, term, context)
                ]
                candidates.extend(filtered_candidates)
            else:
                # 检查页面相关性
                if await self._check_page_relevance(page.title, page.summary, term, context):
                    candidate = LinkingCandidate(
                        mention=term,
                        title=page.title,
                        url=page.fullurl,
                        summary=page.summary[:200],
                        confidence=0.0,
                        is_disambiguation=False
                    )
                    candidates.append(candidate)
            
            return candidates
            
        except Exception as e:
            self.logger.error(f"Wikipedia search failed for term {term}: {e}")
            return []

    def _is_disambiguation_page(self, page) -> bool:
        """检查页面是否为消歧义页面"""
        try:
            # 检查页面类别中是否包含消歧义相关的类别
            if not hasattr(page, 'categories'):
                return False
                
            disambiguation_categories = [
                'Category:Disambiguation pages',
                'Category:All disambiguation pages',
                'Category:All article disambiguation pages'
            ]
            
            for category in page.categories:
                if any(dc.lower() in category.lower() for dc in disambiguation_categories):
                    return True
                    
            # 也可以通过页面内容中的关键词来判断
            if 'may refer to:' in page.text.lower():
                return True
                
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to check disambiguation for page {page.title}: {e}")
            return False

    async def _handle_disambiguation_page(self, disambig_page) -> List[LinkingCandidate]:
        """处理消歧义页面，提取所有可能的具体页面"""
        candidates = []
        try:
            # 获取页面链接
            links = disambig_page.links
            
            for title in list(links.keys())[:10]:  # 限制处理前10个链接
                linked_page = self.wiki.page(title)
                if not linked_page.exists() or self._is_disambiguation_page(linked_page):
                    continue
                    
                candidate = LinkingCandidate(
                    mention="",
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
        
    async def _select_best_match(self, mention: str, context: str, 
                               candidates: List[LinkingCandidate]) -> Optional[LinkingCandidate]:
        """使用 LLM 从候选中选择最佳匹配，增强消歧义处理"""
        if not candidates:
            return None
            
        try:
            # 改进提示以更好地处理消歧义情况
            prompt = f"""{{
                "task": "Entity Linking and Disambiguation",
                "context": "Given a mention from Linux kernel documentation and its context, select the most appropriate Wikipedia page from the candidates. Some candidates might come from disambiguation pages.",
                "mention": "{mention}",
                "original_context": "{context}",
                "candidates": [
                    {self._format_candidates(candidates)}
                ],
                "instructions": "Please analyze each candidate carefully and return a JSON object with:
                    1. 'selected_index': index of the best matching candidate (or -1 if none matches)
                    2. 'confidence': confidence score between 0 and 1
                    3. 'reasoning': brief explanation of your choice, especially if this came from a disambiguation page
                    4. 'disambiguation_source': whether the selected page was from a disambiguation resolution"
            }}"""
            
            # 其余代码保持不变
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
                    # 记录消歧义处理的结果
                    self.logger.info(f"Selected '{selected.title}' with confidence {selected.confidence}. "
                                   f"Reasoning: {result.get('reasoning', 'No reasoning provided')}")
                    return selected
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to select best match for {mention}: {e}")
            return None


    async def _select_best_match_ngrams(self, mentions: list[str], context: str,
                                        ngram_candidates: List[LinkingCandidate]) -> Optional[LinkingCandidate]:
        """使用 LLM 从n-grams候选中选择最佳匹配的一对，增强消歧义处理"""
        if not ngram_candidates:
            return None
            
        try:
            # 改进提示以更好地处理消歧义情况
            prompt = f"""{{
                "task": "Entity Linking and Disambiguation",
                "context": "Given some mentions from Linux kernel documentation and their context, select the most appropriate pair of (mention, Wikipedia page) from the mentions and candidate pages. Please note that the mention and page you choose must describe the EXACT SAME concept. For instance, the mention 'mmu cache' and the page 'memory management unit' are related but NOT describing the exact same concept, while the mention 'mmu' and the page 'memory management unit' are describing the exact same concept. Some candidates might come from disambiguation pages.",
                "mention": "{mentions}",
                "original_context": "{context}",
                "candidate pages": [
                    {self._format_candidates(ngram_candidates)}
                ],
                "instructions": "Please analyze each candidate carefully and return a JSON object with:
                    1. 'selected_index_mention': index of the best matching mention (or -1 if none matches)
                    2. 'selected_index_page': index of the best matching page (or -1 if none matches)
                    3. 'confidence': confidence score between 0 and 1
                    4. 'reasoning': brief explanation of your choice, especially if this came from a disambiguation page
                    5. 'disambiguation_source': whether the selected page was from a disambiguation resolution"
            }}"""
            
            # 其余代码保持不变
            response = await self._get_llm_response(prompt)
            if not response:
                return None
                
            cleaned_response = strip_json(response)
            if not cleaned_response:
                return None
                
            result = json.loads(cleaned_response)
            
            if isinstance(result, dict) and 'selected_index_mention' in result and 'selected_index_page' in result:
                if result['selected_index_mention'] >= 0 and result['selected_index_mention'] < len(mentions) and \
                    result['selected_index_page'] >= 0 and result['selected_index_page'] < len(ngram_candidates):
    
                    selected = ngram_candidates[result['selected_index_page']]
                    selected.mention = mentions[result['selected_index_mention']]                    
                    selected.confidence = result.get('confidence', 0.0)
                    # 记录消歧义处理的结果
                    self.logger.info(f"For mention {selected.mention}: Selected '{selected.title}' with confidence {selected.confidence}. "
                                   f"Reasoning: {result.get('reasoning', 'No reasoning provided')}")
                    return selected
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to select best match for {mentions}: {e}")
            return None


    def _deduplicate_candidates(self, candidates: List[LinkingCandidate]) -> List[LinkingCandidate]:
        """去除重复的候选项"""
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
            
    def _format_candidates(self, candidates: List[LinkingCandidate]) -> str:
        """格式化候选项为 JSON 字符串"""
        return ",".join([
            f"""{{
                "index": {i},
                "title": "{c.title}",
                "url": "{c.url}",
                "summary": "{c.summary}",
                "is_disambiguation": {str(c.is_disambiguation).lower()}
            }}"""
            for i, c in enumerate(candidates)
        ])

    async def _check_page_relevance(self, title: str, content: str, original_term: str, context: str) -> bool:
        """使用LLM判断维基百科页面是否相关"""
        prompt = f"""Given a term from Linux kernel documentation and its context, determine if this Wikipedia page is describing the EXACT SAME concept as used in the Linux context.

        Original term: {original_term}
        Context from documentation: {context[:300]}

        Wikipedia page:
        Title: {title}
        Content: {content[:500]}

        Consider:
        1. Does this Wikipedia page describe the EXACT SAME concept as used in the Linux context? For instance, "handle_pte_fault" and "Page table" are related but NOT the exact same concept.
        2. Is this the technical meaning of the term we're looking for?

        Return only 'true' or 'false'.
        """
        
        try:
            response = await self._get_llm_response(prompt)
            return response.strip().lower() == 'true'
        except Exception as e:
            self.logger.error(f"Failed to check page relevance for {title}: {e}")
            return False