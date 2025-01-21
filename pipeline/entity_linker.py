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
import wikipediaapi  # 添加新的导入
import re
from utils.link_cache import LinkCache
from models.linking import LinkingCandidate
from srctoolkit import Delimiter
import time 



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
            # proxies=self.config.WIKIPEDIA_PROXY_URL
        )
        self.link_cache = LinkCache()
     
    async def  lilink_entity(self, entity, context, feature_id=None, commit_ids=None):
        """链接单个实体到知识库，返回所有可能的匹配结果"""
        start_time = time.time()
        self.logger.info(f"Processing entity linking for: {entity}")
        
        # 1. 生成所有可能的搜索词
        variations_start = time.time()
        
        # 生成变体并合并
        variations = await self._generate_variations(entity, feature_id, commit_ids)
        word_variations = await self._generate_variations(Delimiter.split_camel(entity), feature_id, commit_ids)
        variations.extend(word_variations)
        variations = list(dict.fromkeys(variations))
        
        self.logger.info(f"Variations generation took {time.time() - variations_start:.2f}s")
        
        # 2. 搜索维基百科
        wiki_search_start = time.time()
        primary_candidates = []
        for term in variations:
            wiki_results = await self._search_wikipedia(term, context, feature_id, commit_ids)
            primary_candidates.extend(wiki_results)
        
        primary_candidates = self._deduplicate_candidates(primary_candidates)
        self.logger.info(f"Wikipedia primary search took {time.time() - wiki_search_start:.2f}s")
        
        # 选择最佳匹配
        best_match_start = time.time()
        primary_match = await self._select_best_match(entity, context, primary_candidates)
        self.logger.info(f"Best match selection took {time.time() - best_match_start:.2f}s")
        
        # 3. 处理n-gram子序列匹配
        ngram_start = time.time()
        ngrams = self._generate_ngrams(entity)
        ngram_candidates = []
        
        for ngram in ngrams:
            ngram_variations = await self._generate_variations(ngram, feature_id, commit_ids)
            for term in ngram_variations:
                wiki_results = await self._search_wikipedia(term, context, feature_id, commit_ids)
                ngram_candidates.extend(wiki_results)
        
        ngram_candidates = self._deduplicate_candidates(ngram_candidates)
        self.logger.info(f"N-gram processing took {time.time() - ngram_start:.2f}s")
        
        # 获取所有合理的ngram匹配
        ngram_match_start = time.time()
        ngram_matches = await self._select_valid_ngram_matches(ngrams, context, ngram_candidates)
        self.logger.info(f"N-gram matching took {time.time() - ngram_match_start:.2f}s")

        # 整理结果
        matches = []
        if primary_match and primary_match.confidence > 0.5:
            matches.append({
                'linked_entity': primary_match.title,
                'wikipedia_url': primary_match.url,
                'confidence': primary_match.confidence,
                'search_terms': variations,
                'candidates_count': len(primary_candidates),
                'match_type': 'primary'
            })
        
        for ngram_match in ngram_matches:
            if ngram_match.confidence > 0.5:
                matches.append({
                    'linked_entity': ngram_match.title,
                    'wikipedia_url': ngram_match.url,
                    'confidence': ngram_match.confidence,
                    'search_terms': ngrams,
                    'candidates_count': len(ngram_candidates),
                    'match_type': 'ngram',
                    'matched_ngram': ngram_match.mention
                })

        result = {
            'mention': entity,
            'matches': matches,
            'total_candidates_count': len(primary_candidates) + len(ngram_candidates)
        }
        
        total_time = time.time() - start_time
        self.logger.info(f"Total entity linking process took {total_time:.2f}s for entity: {entity}")
        
        return result
        
    @LinkCache.cached_operation('variations')
    async def _generate_variations(self, mention: str, feature_id: str = None, commit_ids: list = None) -> List[str]:
        """生成术语的变体
        
        Args:
            mention: 需要生成变体的术语
            feature_id: 特征ID，用于缓存
            commit_ids: 提交ID列表，用于缓存
            
        Returns:
            List[str]: 生成的变体列表
        """
        # 只需要实现实际的获取逻辑
        prompt = self._create_variation_prompt(mention)
        response = await self._get_llm_response(prompt)
        return self._parse_variations_response(response, mention)

    def _generate_ngrams(self, text: str, min_n: int = 1, max_n: int = 3) -> List[str]:
        """生成文本的 n-gram 子序列，支持驼峰分割和配置的分隔符"""
        # 首先进行驼峰分割，并按空格分割成列表
        camel_split = Delimiter.split_camel(text)
        words = camel_split.split()
        
        # 如果驼峰分割无效（只有一个词），则使用配置的分隔符
        if len(words) <= 1:
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
        
    def _process_sections(self, page, term, sections, depth=0):
        """递归处理所有层级的章节
        
        Args:
            page: 维基百科页面对象
            term: 搜索词
            sections: 章节列表
            depth: 当前递归深度
        
        Returns:
            List[LinkingCandidate]: 匹配的候选项列表
        """
        candidates = []
        
        for section in sections:
            # 严格匹配：章节标题必须与搜索词完全一致（忽略大小写）
            if section.title.lower() == term.lower():
                # 构建章节的完整路径（用于URL锚点）
                section_path = []
                current = section
                for _ in range(depth + 1):
                    section_path.insert(0, current.title)
                    if not hasattr(current, 'parent'):
                        break
                    current = current.parent
                
                # 创建URL安全的锚点
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
            
            # 递归处理子章节
            if section.sections:
                candidates.extend(self._process_sections(page, term, section.sections, depth + 1))
        
        return candidates

    @LinkCache.cached_operation('main')
    async def _get_wikipedia_page_candidates(self, term: str, feature_id: str = None, 
                                       commit_ids: list = None, *, page=None, 
                                       context: str = None) -> List[LinkingCandidate]:
        """处理维基百科页面并返回候选项
        
        Args:
            term: 搜索词
            feature_id: 特征ID，用于缓存
            commit_ids: 提交ID列表，用于缓存
            page: 维基百科页面对象
            context: 上下文内容
        """
        candidates = []
        
        # 处理所有层级的章节
        candidates = self._process_sections(page, term, page.sections)
        
        if candidates:
            return candidates
            
        # 检查页面相关性
        is_match, confidence = await self._check_page_relevance(
            page.title, 
            page.summary, 
            term, 
            context
        )
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

    async def _search_wikipedia(self, term: str, context: str = None, feature_id: str = None, commit_ids: list = None) -> List[LinkingCandidate]:
        """使用wikipedia-api搜索维基百科，支持章节级别的搜索"""
        try:
            page = self.wiki.page(term)
            candidates = []
            
            if not page.exists():
                return []
            
            if self._is_disambiguation_page(page):
                candidates.extend(await self._handle_disambiguation_with_relevance(
                    term, feature_id, commit_ids, page=page, context=context
                ))
            else:
                # 使用装饰器处理的函数获取主搜索结果
                page_candidates = await self._get_wikipedia_page_candidates(
                    term, feature_id=feature_id, commit_ids=commit_ids, 
                    page=page, context=context
                )
                candidates.extend(page_candidates)
            
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

    @LinkCache.cached_operation('disambig')
    async def _handle_disambiguation_with_relevance(self, term: str, feature_id: str = None, 
                                              commit_ids: list = None, *, page=None, 
                                              context: str = None) -> List[LinkingCandidate]:
        """处理消歧义页面并检查相关性
        
        Args:
            term: 搜索词
            feature_id: 特征ID，用于缓存
            commit_ids: 提交ID列表，用于缓存
            page: 维基百科页面对象
            context: 上下文内容
        """
        disambig_candidates = self._handle_disambiguation_page(term, page)
        filtered_candidates = []
        
        for candidate in disambig_candidates:
            is_match, confidence = await self._check_page_relevance(
                candidate.title, 
                candidate.summary, 
                term, 
                context
            )
            if is_match:
                candidate.confidence = confidence
                filtered_candidates.append(candidate)
        
        return filtered_candidates

    def _handle_disambiguation_page(self,mention, disambig_page) -> List[LinkingCandidate]:
        """处理消歧义页面，提取所有可能的具体页面"""
        candidates = []
        try:
            # 获取页面链接
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


    async def _select_valid_ngram_matches(self, mentions: list[str], context: str,
                                        ngram_candidates: List[LinkingCandidate]) -> List[LinkingCandidate]:
        """从n-grams候选中选择所有合理的匹配"""
        if not ngram_candidates:
            return []
        
        try:
            # Improved prompt formatting to ensure valid JSON response
            prompt = f"""Given mentions from Linux kernel documentation and their context, select appropriate pairs of (mention, Wikipedia page).
            
            Mentions: {json.dumps(mentions)}
            Context: {context}
            Candidates: {self._format_candidates(ngram_candidates)}
            
            Return a JSON array of matches in this exact format:
            [
                {{
                    "mention_index": <index of matching mention>,
                    "page_index": <index of matching page>,
                    "confidence": <score between 0 and 1>,
                    "reasoning": "<brief explanation>"
                }}
            ]
            
            Only include pairs where the mention and page describe the exact same concept."""
            
            response = await self._get_llm_response(prompt)
            if not response:
                return []
            
            # More robust JSON parsing
            try:
                # First try to find JSON array within the response
                json_start = response.find('[')
                json_end = response.rfind(']') + 1
                if json_start >= 0 and json_end > json_start:
                    cleaned_response = response[json_start:json_end]
                else:
                    cleaned_response = strip_json(response)
                
                results = json.loads(cleaned_response)
                
            except json.JSONDecodeError:
                self.logger.error(f"Failed to parse JSON response: {response}")
                return []
            
            valid_matches = []
            
            for result in results:
                if isinstance(result, dict) and 'mention_index' in result and 'page_index' in result:
                    if (0 <= result['mention_index'] < len(mentions) and 
                        0 <= result['page_index'] < len(ngram_candidates)):
                        
                        selected = ngram_candidates[result['page_index']]
                        selected.mention = mentions[result['mention_index']]
                        selected.confidence = result.get('confidence', 0.0)
                        valid_matches.append(selected)
                        
                        self.logger.info(f"Matched: {selected.mention} -> {selected.title} "
                                       f"(confidence: {selected.confidence})")
            
            return valid_matches
            
        except Exception as e:
            self.logger.error(f"Failed to select valid matches for {mentions}: {str(e)}")
            return []


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
        """格式化候选项为 JSON 字符串
        
        Args:
            candidates: 候选项列表，可以是 LinkingCandidate 对象或字符串
            
        Returns:
            格式化后的 JSON 字符串
        """
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

    async def _check_page_relevance(self, title: str, content: str, original_term: str, context: str) -> Tuple[bool, float]:
        """使用LLM判断维基百科页面是否相关，并提供分析依据
        
        Returns:
            Tuple[bool, float]: 返回(是否匹配, 置信度)的元组
        """
        prompt = f"""Given a term from Linux kernel documentation and its context, analyze if this Wikipedia page appropriately matches the concept as used in the Linux context.

        Original term: {original_term}
        Context from documentation: {context[:300]}

        Wikipedia page:
        Title: {title}
        Content: {content[:500]}

        Consider:
        1. Does this Wikipedia page describe the same concept or a directly relevant concept as used in the Linux context?
        2. While they don't need to be exactly identical, the core concept should match. For example:
           - Good match: "MMU" and "Memory Management Unit" (one is abbreviation of the other)
           - Poor match: "handle_pte_fault" and "Page table" (only indirectly related)
        3. Is this the technical meaning of the term we're looking for?

        Return a JSON object with the following structure:
        {{
            "linux_meaning": "Brief explanation of the term's meaning in Linux context",
            "wiki_meaning": "Brief explanation of the Wikipedia page's concept",
            "confidence": 0-1, // A value between 0 and 1 indicating how confident we are in the match, where 0 means no confidence and 1 means complete confidence
            "reasoning": "Brief explanation of why they match or don't match",
            "is_match": true/false
        }}
        """
        
        try:
            response = await self._get_llm_response(prompt)
            cleaned_response = strip_json(response)
            result = json.loads(cleaned_response)
            
            # 记录详细分析结果
            self.logger.info(f"Relevance analysis for {original_term} -> {title}:\n{json.dumps(result, indent=2)}")
            
            is_match = result.get('is_match', False)
            confidence = result.get('confidence', 0.0)
            
            return is_match, confidence
            
        except Exception as e:
            self.logger.error(f"Failed to check page relevance for {title}: {e}")
            return False, 0.0