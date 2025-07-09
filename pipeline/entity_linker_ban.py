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
import sqlite3
import wikitextparser as wtp
import random
from functools import wraps


class RateLimiter:
    """请求限流器，控制API调用频率"""
    def __init__(self, max_requests_per_minute=60, max_requests_per_hour=3600):
        self.max_requests_per_minute = max_requests_per_minute
        self.max_requests_per_hour = max_requests_per_hour
        self.requests_per_minute = []
        self.requests_per_hour = []
        self.last_request_time = 0
    
    async def wait_if_needed(self):
        """检查是否需要等待以避免超过限流"""
        current_time = time.time()
        
        # 清理过期的请求记录
        minute_ago = current_time - 60
        hour_ago = current_time - 3600
        
        self.requests_per_minute = [t for t in self.requests_per_minute if t > minute_ago]
        self.requests_per_hour = [t for t in self.requests_per_hour if t > hour_ago]
        
        # 检查是否需要等待
        wait_time = 0
        
        # 每分钟限制
        if len(self.requests_per_minute) >= self.max_requests_per_minute:
            wait_time = max(wait_time, 60 - (current_time - self.requests_per_minute[0]))
        
        # 每小时限制
        if len(self.requests_per_hour) >= self.max_requests_per_hour:
            wait_time = max(wait_time, 3600 - (current_time - self.requests_per_hour[0]))
        
        # 最小请求间隔（避免过于频繁的请求）
        min_interval = 1.0  # 最少等待1秒
        if current_time - self.last_request_time < min_interval:
            wait_time = max(wait_time, min_interval - (current_time - self.last_request_time))
        
        if wait_time > 0:
            # 添加一些随机性避免多个进程同时请求
            jitter = random.uniform(0, 0.5)
            total_wait = wait_time + jitter
            await asyncio.sleep(total_wait)
            current_time = time.time()
        
        # 记录这次请求
        self.requests_per_minute.append(current_time)
        self.requests_per_hour.append(current_time)
        self.last_request_time = current_time


def retry_with_backoff(max_retries=5, base_delay=1.0, max_delay=300.0):
    """装饰器：为函数添加重试和指数退避机制"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    # 检查是否是429错误或其他可重试的错误
                    if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 429:
                        # 429错误，需要等待更长时间
                        delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                        if hasattr(args[0], 'logger'):
                            args[0].logger.warning(f"Rate limited (429), retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                    elif attempt < max_retries - 1:
                        # 其他错误，短暂等待后重试
                        delay = min(base_delay * (2 ** attempt), max_delay / 10)
                        if hasattr(args[0], 'logger'):
                            args[0].logger.warning(f"Request failed: {e}, retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                    else:
                        # 最后一次尝试仍然失败
                        if hasattr(args[0], 'logger'):
                            args[0].logger.error(f"Max retries ({max_retries}) exceeded for request: {e}")
                        raise
            return None
        return wrapper
    return decorator


class EntityLinker:
    def __init__(self, config):
        self.logger = setup_logger('entity_linker', file_output=True)
        self.config = config
        self.llm = deepseek()
        
        # 修改本地数据库配置的获取方式
        self.use_local_db = getattr(self.config, 'USE_LOCAL_WIKIPEDIA', False)
        
        # 添加本地MediaWiki API配置
        self.local_wiki_api = getattr(self.config, 'LOCAL_WIKI_API', 'http://10.176.37.1:6101/api.php')
        
        # 从配置获取限流参数
        rate_limit_config = getattr(self.config, 'WIKIPEDIA_RATE_LIMIT', {})
        self.rate_limiter = RateLimiter(
            max_requests_per_minute=rate_limit_config.get('max_requests_per_minute', 20),
            max_requests_per_hour=rate_limit_config.get('max_requests_per_hour', 1200)
        )
        
        # 从配置获取User-Agent
        user_agent = getattr(self.config, 'WIKIPEDIA_USER_AGENT', 
                           'LinuxKernelKG/1.0 (Educational research project; Linux kernel knowledge graph; contact: admin@example.com) Python/3.x')
        
        # 改进的Wikipedia API初始化，使用配置的User-Agent
        self.wiki = wikipediaapi.Wikipedia(
            language='en',
            extract_format=wikipediaapi.ExtractFormat.HTML,
            user_agent=user_agent,
        )
        self.link_cache = LinkCache()
        
        # API调用统计
        self.api_stats = {
            'total_requests': 0,
            'cached_requests': 0,
            'failed_requests': 0,
            'rate_limited_requests': 0,
            'session_start_time': time.time()
        }
        
        # 从配置获取其他参数
        self.enable_api_logging = getattr(self.config, 'ENABLE_API_LOGGING', True)
        self.auto_adjust_rate_limit = getattr(self.config, 'AUTO_ADJUST_RATE_LIMIT', True)
        
        self.logger.info(f"EntityLinker initialized with rate limits: {rate_limit_config.get('max_requests_per_minute', 20)}/min, {rate_limit_config.get('max_requests_per_hour', 1200)}/hour")

    def log_api_stats(self):
        """记录API调用统计"""
        if not self.enable_api_logging:
            return
            
        session_duration = time.time() - self.api_stats['session_start_time']
        avg_requests_per_minute = (self.api_stats['total_requests'] / max(session_duration / 60, 1))
        
        stats_info = {
            **self.api_stats,
            'session_duration_minutes': round(session_duration / 60, 2),
            'avg_requests_per_minute': round(avg_requests_per_minute, 2)
        }
        
        self.logger.info(f"API Statistics: {json.dumps(stats_info, indent=2)}")
        
        # 如果平均请求频率过高，建议调整
        if avg_requests_per_minute > self.rate_limiter.max_requests_per_minute * 0.8:
            self.logger.warning(f"Request rate ({avg_requests_per_minute:.1f}/min) is approaching limit ({self.rate_limiter.max_requests_per_minute}/min). Consider reducing batch sizes.")

    async def link_entity(self, entity):
        """链接单个实体到知识库，返回所有可能的匹配结果"""
        start_time = time.time()
        self.logger.info(f"Processing entity linking for: {entity}")
        entity_name = entity.name
        context = entity.context
        feature_id = entity.feature_id
        commit_ids = entity.commit_ids
        entities = []
        
        # 1. 检查缓存以减少重复处理
        cache_key = f"{entity_name}_{hash(context or '')}"
        
        # 2. 生成所有可能的搜索词
        variations_start = time.time()
        
        # 生成变体并合并
        variations = await self._generate_variations(entity_name, context, feature_id, commit_ids)
        
        self.logger.info(f"Variations generation took {time.time() - variations_start:.2f}s")
        
        # 3. 去重变体以减少API调用
        unique_variations = list(dict.fromkeys(variations))
        if len(variations) != len(unique_variations):
            self.logger.info(f"Reduced variations from {len(variations)} to {len(unique_variations)} after deduplication")
           
        # 4. 搜索维基百科（带限流）
        wiki_search_start = time.time()
        primary_candidates = []
        
        for term in unique_variations:
            # 为每个搜索术语添加限流
            await self.rate_limiter.wait_if_needed()
            wiki_results = await self._search_wikipedia(term, context, feature_id, commit_ids)
            primary_candidates.extend(wiki_results)
            
            # 添加进度日志
            if len(unique_variations) > 5:
                self.logger.info(f"Processed {unique_variations.index(term) + 1}/{len(unique_variations)} variations for entity: {entity_name}")
        
        primary_candidates = self._deduplicate_candidates(primary_candidates)
        self.logger.info(f"Wikipedia primary search took {time.time() - wiki_search_start:.2f}s")
        
        # 5. 选择最佳匹配
        best_match_start = time.time()
        primary_match = await self._select_best_match(entity, context, primary_candidates)
        self.logger.info(f"Best match selection took {time.time() - best_match_start:.2f}s")

        # 6. 整理结果
        matches = []
        if primary_match and primary_match.confidence > 0.5:
            entity.add_external_link('wikipedia',[primary_match.url])
            entity.description = primary_match.summary
            # 补充逻辑，如果entity.name和primary_match.title不一致，则将primary_match.title作为entity.name,并将entity.name作为别名
            if entity.name != primary_match.title:
                entity.add_alias(primary_match.title)
        
            entities.append(entity)
        
        total_time = time.time() - start_time
        self.logger.info(f"Total entity linking process took {total_time:.2f}s for entity: {entity}")
        
        # 定期记录API统计
        if self.api_stats['total_requests'] % 50 == 0:
            self.log_api_stats()
        
        return entities

    @LinkCache.cached_operation('variations')
    async def _generate_variations(self, mention: str,context: str = None, feature_id: str = None, commit_ids: list = None) -> List[str]:
        """生成术语的变体
        
        Args:
            mention: 需要生成变体的术语
            feature_id: 特征ID，用于缓存
            commit_ids: 提交ID列表，用于缓存
            
        Returns:
            List[str]: 生成的变体列表
        """
        # 只需要实现实际的获取逻辑
        prompt = self._create_variation_prompt(mention, context)
        response = await self._get_llm_response(prompt)
        variations = self._parse_variations_response(response, mention)
        variations.append(mention)
        variations = list(dict.fromkeys(variations))
        return variations
 
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

    # @LinkCache.cached_operation('main')
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
        
        # 1. 首先尝试在章节中查找精确匹配
        section_title,section_text,is_find = await self._find_matching_sections(page, term)
        # if section_title:
        #     return section_title,section_text
            
        # 2. 如果没有找到章节匹配，检查页面相关性
        is_match, confidence = await self._check_page_relevance(
            section_title, 
            section_text, 
            term, 
            context
        )
        if is_match:
            candidate = LinkingCandidate(
                mention=term,
                title=section_title,
                url=page.fullurl+("#"+section_title if is_find else ''),
                summary=section_text,
                confidence=confidence,
                is_disambiguation=False
            )
            candidates.append(candidate)
            
        return candidates

    async def _find_matching_sections(self, page, term: str) -> Tuple[str, str]:
        """查找匹配的章节并返回章节的标题和摘要
        
        Args:
            page: 维基百科页面对象
            term: 搜索词
            
        Returns:
            Tuple[str, str]: 匹配章节的标题和摘要，如未找到则返回页面的标题和摘要
        """
        
        # 定义深度优先搜索函数
        def search_sections(sections):
            for section in sections:
                # 检查章节标题是否匹配搜索词（忽略大小写）
                if section.title.lower() == term.lower():
                    return section.title, section.text,True
                
                # 递归搜索子章节
                if section.sections:
                    result = search_sections(section.sections)
                    if result[0] is not None:  # 如果找到匹配，立即返回结果
                        return result
            
            # 当前层级未找到匹配
            return None, None,False
        
        # 开始搜索所有章节
        result = search_sections(page.sections)
        
        # 如果找到匹配的章节，返回其标题和内容；否则返回页面的标题和摘要
        if result[0] is not None:
            return result
        else:
            return page.title, page.summary,False

    async def _search_wikipedia(self, term: str, context: str = None, feature_id: str = None, commit_ids: list = None) -> List[LinkingCandidate]:
        """搜索维基百科，根据配置使用本地数据库或在线API"""
        if self.use_local_db:
            return await self._search_wikipedia_local(term, context, feature_id, commit_ids)
        else:
            return await self._search_wikipedia_online(term, context, feature_id, commit_ids)

    @retry_with_backoff(max_retries=3, base_delay=2.0, max_delay=60.0)
    async def _search_wikipedia_online(self, term: str, context: str = None, feature_id: str = None, commit_ids: list = None) -> List[LinkingCandidate]:
        """使用在线Wikipedia API搜索，包含限流和重试机制"""
        
        # 应用限流
        await self.rate_limiter.wait_if_needed()
        self.api_stats['total_requests'] += 1

        try:
            # 首先尝试查找消歧义页面
            disambig_term = f"{term}_(disambiguation)"
            await self.rate_limiter.wait_if_needed()  # 为每个API调用添加限流
            
            disambig_page = self.wiki.page(disambig_term)
            if disambig_page.exists():
                self.logger.info(f"Found disambiguation page: {disambig_term}")
                return await self._handle_disambiguation_with_relevance(
                    term, feature_id, commit_ids, page=disambig_page, context=context
                )
            
            # 如果没有消歧义页面，尝试直接查找页面
            await self.rate_limiter.wait_if_needed()  # 为每个API调用添加限流
            page = self.wiki.page(term)
            candidates = []
            
            if not page.exists():
                self.logger.info(f"No Wikipedia page exists for term: {term}")
                return []
            
            if self._is_disambiguation_page(page):
                # 页面本身是消歧义页
                self.logger.info(f"Found disambiguation page for term: {term}")
                candidates.extend(await self._handle_disambiguation_with_relevance(
                    term, feature_id, commit_ids, page=page, context=context
                ))
            else:
                page_candidates = await self._get_wikipedia_page_candidates(
                    term, feature_id=feature_id, commit_ids=commit_ids, page=page, context=context
                )
                candidates.extend(page_candidates)
            
            return candidates
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                self.api_stats['rate_limited_requests'] += 1
                self.logger.warning(f"Rate limited (429) for term: {term}")
                raise  # 让装饰器处理重试
            else:
                self.api_stats['failed_requests'] += 1
                self.logger.error(f"HTTP error for term {term}: {e}")
                return []
        except Exception as e:
            self.api_stats['failed_requests'] += 1
            self.logger.error(f"Wikipedia online search failed for term {term}: {e}")
            return []

    async def _search_wikipedia_local(self, term: str, context: str = None, feature_id: str = None, commit_ids: list = None) -> List[LinkingCandidate]:
        """使用本地MediaWiki API搜索维基百科页面"""
        try:
            self.logger.info(f"Searching local MediaWiki for term: {term}")
            
            # 首先检查页面是否存在
            if not self._check_page_exists_local(term):
                self.logger.info(f"Page does not exist in local MediaWiki: {term}")
                return []
            
            # 构建MediaWiki API请求 - 使用基本参数
            api_url = self.local_wiki_api
            params = {
                'action': 'query',
                'format': 'json',
                'titles': term,
                'prop': 'info|categories',  # 移除不支持的extracts和sections
                'inprop': 'url',
                'redirects': '1',
            }
            
            # 发送请求
            response = requests.get(api_url, params=params)
            self.logger.debug(f"API response for query: {response.text[:500]}")
            data = response.json()
            
            # 检查是否有错误
            if 'error' in data:
                self.logger.warning(f"API error for query {term}: {data['error']}")
                return []
            
            # 获取页面内容 - 单独请求
            content_params = {
                'action': 'parse',
                'format': 'json',
                'page': term,
                'prop': 'text',  # 简化请求参数
                'formatversion': '2',
            }
            
            content_data = {}
            try:
                content_response = requests.get(api_url, params=content_params)
                self.logger.debug(f"API response for parse: {content_response.text[:500]}")
                content_data = content_response.json()
                
                # 检查是否有错误
                if 'error' in content_data:
                    self.logger.warning(f"API error for parse {term}: {content_data['error']}")
                    # 继续处理，但content_data为空字典
                    content_data = {}
            except Exception as e:
                self.logger.error(f"Failed to get content for term {term}: {e}")
                # 继续处理，但content_data为空字典
            
            # 处理结果
            candidates = []
            if 'query' in data and 'pages' in data['query']:
                pages = data['query']['pages']
                
                # MediaWiki API返回的是字典，键是页面ID
                for page_id, page_data in pages.items():
                    # 跳过不存在的页面
                    if int(page_id) < 0:
                        self.logger.info(f"No local MediaWiki page exists for term: {term}")
                        continue
                    
                    # 获取页面内容
                    page_content = ''
                    page_summary = ''
                    page_title = page_data.get('title', '')
                    
                    # 尝试从parse响应中提取文本
                    if 'parse' in content_data:
                        if 'text' in content_data['parse']:
                            raw_content = content_data['parse']['text']
                            
                            # 处理不同的响应格式
                            if isinstance(raw_content, str):
                                page_content = raw_content
                            elif isinstance(raw_content, dict) and '*' in raw_content:
                                page_content = raw_content['*']
                            else:
                                self.logger.warning(f"Unexpected content format: {type(raw_content)}")
                                page_content = str(raw_content)
                            
                            # 提取文本的第一段作为摘要
                            try:
                                soup = BeautifulSoup(page_content, 'html.parser')
                                # 移除脚本和样式元素
                                for script in soup(["script", "style"]):
                                    script.extract()
                                
                                paragraphs = soup.find_all('p')
                                if paragraphs:
                                    page_summary = paragraphs[0].get_text().strip()[:200]
                                else:
                                    # 如果没有段落，尝试获取任何文本
                                    page_summary = soup.get_text().strip()[:200]
                            except Exception as e:
                                self.logger.error(f"Failed to parse HTML content: {e}")
                                # 应急措施：直接提取一小部分内容作为摘要
                                page_summary = page_content.replace('<', ' ').replace('>', ' ')[:200]
                    
                    # 构造模拟的页面对象，与online版本保持一致
                    page = self._create_page_object_from_api_data_basic(
                        page_data, 
                        page_content, 
                        page_summary,
                        api_url
                    )
                    
                    # 检查是否为消歧义页面
                    is_disambiguation = self._is_disambiguation_page_local(page)
                    
                    if is_disambiguation:
                        self.logger.info(f"Found local disambiguation page for term: {term}")
                        # 处理消歧义页面 - 可能返回多个候选项
                        disambig_candidates = await self._handle_disambiguation_with_relevance(
                            term, feature_id, commit_ids, page=page, context=context
                        )
                        candidates.extend(disambig_candidates)
                    else:
                        # 处理普通页面
                        page_candidates = await self._get_wikipedia_page_candidates(
                            term, feature_id=feature_id, commit_ids=commit_ids, page=page, context=context
                        )
                        candidates.extend(page_candidates)
            
            return candidates
            
        except Exception as e:
            self.logger.error(f"Local MediaWiki search failed for term {term}: {e}")
            return []

    def _create_page_object_from_api_data_basic(self, page_data, page_content, page_summary, api_base_url):
        """从基本的MediaWiki API数据创建页面对象"""
        class MediaWikiPage:
            def __init__(self, data, content, summary, api_url):
                self.pageid = data.get('pageid')
                self.title = data.get('title', '')
                self.summary = summary
                self.content = content
                self.text = content
                
                # 构建URL
                self.fullurl = data.get('fullurl', '')
                if not self.fullurl and 'title' in data:
                    wiki_url = api_base_url.replace('api.php', 'index.php')
                    self.fullurl = f"{wiki_url}?title={data['title'].replace(' ', '_')}"
                
                # 处理类别
                self.categories = []
                if 'categories' in data:
                    self.categories = [cat.get('title', '') for cat in data.get('categories', [])]
                
                # 没有章节信息时设置空列表
                self.sections = []
        
        return MediaWikiPage(page_data, page_content, page_summary, api_base_url)
    
    def _is_disambiguation_page(self, page) -> bool:
        """检查页面是否为消歧义页面或包含指向消歧义页面的链接"""
        try:
            # 检查页面类别中是否包含消歧义相关的类别
            if hasattr(page, 'categories'):
                disambiguation_categories = [
                    'Category:Disambiguation pages',
                    'Category:All disambiguation pages',
                    'Category:All article disambiguation pages'
                ]
                
                for category in page.categories:
                    if isinstance(category, str) and any(dc.lower() in category.lower() for dc in disambiguation_categories):
                        return True
                    
            # 通过页面内容关键词判断
            if hasattr(page, 'text') and isinstance(page.text, str):
                if 'may refer to:' in page.text.lower():
                    return True
        
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to check disambiguation for page {getattr(page, 'title', 'unknown')}: {e}")
            return False
    
    def _is_disambiguation_page_local(self, page):
        """检查本地MediaWiki页面是否为消歧义页面"""
        try:
            # 检查页面类别
            disambiguation_keywords = ['disambiguation', 'disambig']
            
            # 检查类别
            if hasattr(page, 'categories') and page.categories:
                for category in page.categories:
                    if any(keyword in category.lower() for keyword in disambiguation_keywords):
                        return True
            
            # 检查页面内容
            if hasattr(page, 'text') and page.text:
                # 常见的消歧义页面标志
                disambig_patterns = [
                    'may refer to:',
                    'can refer to:',
                    'may mean:',
                    'may stand for:',
                    'is a disambiguation page',
                    'disambiguation page',
                    'refers to:',
                    'can mean:'
                ]
                
                for pattern in disambig_patterns:
                    if pattern in page.text.lower():
                        return True
                
                # 检查页面标题是否包含(disambiguation)
                if hasattr(page, 'title') and '(disambiguation)' in page.title.lower():
                    return True
                
                # 检查页面是否包含多个"may refer to"链接
                if page.text.count('<li>') > 5 and page.text.count('<a href') > 5:
                    try:
                        # 检查是否有列表结构
                        soup = BeautifulSoup(page.text, 'html.parser')
                        list_items = soup.find_all('li')
                        if len(list_items) > 5:
                            # 如果有大量列表项，每项都包含链接，很可能是消歧义页面
                            links_in_items = sum(1 for item in list_items if item.find('a'))
                            if links_in_items > 0.7 * len(list_items):  # 70%以上的列表项都包含链接
                                return True
                    except Exception as e:
                        self.logger.error(f"Error parsing page for disambiguation check: {e}")
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to check disambiguation for local page {getattr(page, 'title', 'unknown')}: {e}")
            return False

    def _handle_disambiguation_page(self, mention, disambig_page) -> List[LinkingCandidate]:
        """处理消歧义页面，根据配置选择本地或在线方式"""
        if self.use_local_db:
            return self._handle_disambiguation_page_local(mention, disambig_page)
        else:
            return self._handle_disambiguation_page_online(mention, disambig_page)

    def _handle_disambiguation_page_online(self, mention, disambig_page) -> List[LinkingCandidate]:
        """使用在线API处理消歧义页面（原有逻辑）"""
        candidates = []
        try:
            links = disambig_page.links
            
            for index, title in enumerate(list(links.keys())):
                try:
                    linked_page = links[title]
                    candidate = LinkingCandidate(
                        mention=mention,
                        title=linked_page.title,
                        url=getattr(linked_page, 'fullurl', getattr(disambig_page, 'fullurl', '')),
                        summary=linked_page.summary[:500],
                        confidence=0.0,
                        page=linked_page,
                        is_disambiguation=False
                    )
                    candidates.append(candidate)
                except Exception as e:
                    # 单个链接处理失败时，记录错误但继续处理其他链接
                    self.logger.warning(f"Failed to process link '{title}': {e}")
                    continue
        except Exception as e:
            self.logger.error(f"Failed to handle disambiguation page {disambig_page.title}: {e}")
        return candidates

    def _handle_disambiguation_page_local(self, mention, disambig_page) -> List[LinkingCandidate]:
        """使用本地MediaWiki API处理消歧义页面
        
        Args:
            mention: 原始提及词
            disambig_page: 消歧义页面对象
            
        Returns:
            List[LinkingCandidate]: 候选项列表
        """
        candidates = []
        try:
            self.logger.info(f"Handling local disambiguation page for: {mention}")
            
            # 构建MediaWiki API请求获取页面链接
            api_url = self.local_wiki_api
            params = {
                'action': 'query',
                'format': 'json',
                'titles': disambig_page.title,
                'prop': 'links',
                'pllimit': '500',  # 最多获取500个链接
            }
            
            # 发送请求
            response = requests.get(api_url, params=params)
            self.logger.debug(f"API response for links: {response.text[:500]}")
            data = response.json()
            
            # 提取链接
            links = []
            if 'query' in data and 'pages' in data['query']:
                for page_id, page_data in data['query']['pages'].items():
                    if 'links' in page_data:
                        for link in page_data['links']:
                            # 跳过特殊页面链接
                            if not any(ns in link['title'] for ns in ['Category:', 'File:', 'Image:', 'Special:', 'Template:']):
                                links.append(link['title'])
            
            # 批量获取链接指向的页面信息
            if links:
                self.logger.info(f"Found {len(links)} links in disambiguation page for: {mention}")
                
                # 批量处理，每次最多50个链接
                batch_size = 50
                for i in range(0, len(links), batch_size):
                    batch_links = links[i:i+batch_size]
                    batch_titles = '|'.join(batch_links)
                    
                    # 使用基本参数
                    params = {
                        'action': 'query',
                        'format': 'json',
                        'titles': batch_titles,
                        'prop': 'info|categories',  # 移除不支持的extracts
                        'inprop': 'url',
                        'redirects': '1',
                    }
                    
                    batch_response = requests.get(api_url, params=params)
                    batch_data = batch_response.json()
                    
                    # 处理结果
                    if 'query' in batch_data and 'pages' in batch_data['query']:
                        for page_id, page_data in batch_data['query']['pages'].items():
                            # 跳过不存在的页面
                            if int(page_id) < 0:
                                continue
                            
                            # 获取页面内容和摘要 - 单独请求
                            page_title = page_data.get('title', '')
                            
                            # 首先检查页面是否存在
                            if not self._check_page_exists_local(page_title):
                                self.logger.info(f"Page does not exist in local MediaWiki: {page_title}")
                                continue
                            
                            # 获取页面内容
                            content_params = {
                                'action': 'parse',
                                'format': 'json',
                                'page': page_title,
                                'prop': 'text',
                                'formatversion': '2',
                            }
                            
                            try:
                                content_response = requests.get(api_url, params=content_params)
                                content_data = content_response.json()
                                
                                # 检查是否有错误
                                if 'error' in content_data:
                                    self.logger.warning(f"API error for page {page_title}: {content_data['error']}")
                                    continue
                                
                                page_content = ''
                                page_summary = ''
                                
                                # 尝试从parse响应中提取文本
                                if 'parse' in content_data and 'text' in content_data['parse']:
                                    raw_content = content_data['parse']['text']
                                    
                                    # 处理不同的响应格式
                                    if isinstance(raw_content, str):
                                        page_content = raw_content
                                    elif isinstance(raw_content, dict) and '*' in raw_content:
                                        page_content = raw_content['*']
                                    else:
                                        page_content = str(raw_content)
                                    
                                    # 提取文本的第一段作为摘要
                                    try:
                                        soup = BeautifulSoup(page_content, 'html.parser')
                                        # 移除脚本和样式元素
                                        for script in soup(["script", "style"]):
                                            script.extract()
                                        
                                        paragraphs = soup.find_all('p')
                                        if paragraphs:
                                            page_summary = paragraphs[0].get_text().strip()[:200]
                                        else:
                                            # 如果没有段落，尝试获取任何文本
                                            page_summary = soup.get_text().strip()[:200]
                                    except Exception as e:
                                        self.logger.error(f"Failed to parse HTML content: {e}")
                                        # 应急措施：直接提取一小部分内容作为摘要
                                        page_summary = page_content.replace('<', ' ').replace('>', ' ')[:200]
                            except Exception as e:
                                self.logger.error(f"Failed to get content for page {page_title}: {e}")
                                continue  # 跳过此页面
                            
                            # 检查是否为消歧义页面
                            page = self._create_page_object_from_api_data_basic(page_data, page_content, page_summary, api_url)
                            is_disambig = self._is_disambiguation_page_local(page)
                            
                            # 跳过消歧义页面
                            if is_disambig:
                                continue
                            
                            # 创建候选项
                            candidate = LinkingCandidate(
                                mention=mention,
                                title=page.title,
                                url=getattr(page, 'fullurl', 'https://default-url.com'),
                                summary=page_summary,
                                confidence=0.0,
                                is_disambiguation=False
                            )
                            candidates.append(candidate)
            
            return candidates
            
        except Exception as e:
            self.logger.error(f"Failed to handle local disambiguation page {getattr(disambig_page, 'title', 'unknown')}: {e}")
            return []

    @LinkCache.cached_operation('disambig')
    async def _filter_domain_relevant_pages(self, term: str,feature_id: str = None, commit_ids: list = None,page=None) -> List[LinkingCandidate]:
        """预筛选与Linux/计算机领域相关的页面
        
        Args:
            term: 原始搜索词
            page: 当前页面
        Returns:
            List[LinkingCandidate]: 与领域相关的候选项列表
        """

        # 批量处理未缓存的候选项
        prompt = """Analyze these Wikipedia pages and determine if each is related to Linux, operating systems, 
        computer software, or computer hardware. Consider both direct and indirect but meaningful relationships.

        Pages to analyze:
        {candidates_json}

        For each page, return a JSON object list:
        [
            {
                "index": index num in candidates_json parameter,
                "is_domain_relevant": true/false
               
            },
            ...
        ]

        Consider the following categories as relevant:

        Direct Relevance (Strong Connection):
        1. Linux kernel, distributions, or Linux-specific components
        2. Operating system concepts, architectures, or implementations
        3. Computer hardware components that interact with operating systems
        4. Low-level software or system programming
        5. System calls, APIs, and protocols used in operating systems

        Indirect but Important Relevance:
        1. General computing concepts that are frequently used in OS context
        2. Programming paradigms and patterns common in system development
        3. Development tools and utilities essential for kernel development
        4. Security concepts and mechanisms relevant to OS
        5. Performance optimization and system resource management
        6. Networking concepts that interact with the kernel
        7. File systems and storage technologies
        8. Process and thread management related concepts

        Guidelines:
        - Mark as relevant if the concept is commonly used or referenced in kernel development
        - Include fundamental computer science concepts that are essential to understanding OS
        - Consider the practical application in system programming
        - If in doubt about relevance, check if the concept appears in Linux kernel documentation
        """

        # 获取所有消歧义候选项，但添加限流
        await self.rate_limiter.wait_if_needed()
        candidates = self._handle_disambiguation_page(term, page)

        # 添加请求去重机制
        unique_candidates = self._deduplicate_candidates(candidates)
        self.logger.info(f"Reduced candidates from {len(candidates)} to {len(unique_candidates)} after deduplication")

        # 分批处理，每批减少到15个以降低单次处理负担
        BATCH_SIZE = 15
        domain_relevant_candidates = []
        # 构建候选项JSON
        candidates_json = []
        for i, candidate in enumerate(unique_candidates):
            # 移除多余的格式化和引号，直接使用字典
            candidate_dict = {
                "index": i,
                "title": candidate.title,
                "summary": candidate.summary[:300] if candidate.summary else ""  # 减少摘要长度以降低token消耗
            }
            candidates_json.append(json.dumps(candidate_dict))

    
        for i in range(0, len(candidates_json), BATCH_SIZE):
            batch = candidates_json[i:i+BATCH_SIZE]
            candidates_json_str = ",".join(batch)
            formatted_prompt = prompt.replace("{candidates_json}", candidates_json_str)
            
            try:
                # 为LLM调用也添加一定的延迟，避免过于频繁的调用
                await asyncio.sleep(0.5)
                response = await self._get_llm_response(formatted_prompt)
                cleaned_response = strip_json(response)
                results = json.loads(cleaned_response)

                # 处理结果并更新缓存
                for result in results:
                    if isinstance(result, dict) and "index" in result:
                        index = result.get("index")
                        if 0 <= index < len(unique_candidates):
                            candidate = unique_candidates[index]
                            candidate.page = unique_candidates[index].page
                            is_relevant = result.get("is_domain_relevant", False)
                            
                            if is_relevant:
                                domain_relevant_candidates.append(candidate)
                                self.logger.info(f"Domain relevant page found: {candidate.title} - {candidate.summary[:100]}...")

            except Exception as e:
                self.logger.error(f"Failed to process domain relevance batch: {e}")
                # 出错时保守处理：将该批次的所有候选项都视为可能相关

        # 合并缓存的和新处理的结果
        return domain_relevant_candidates

    async def _handle_disambiguation_with_relevance(self, term: str, feature_id: str = None, 
                                              commit_ids: list = None, *, page=None, 
                                              context: str = None) -> List[LinkingCandidate]:
        """处理消歧义页面并检查相关性"""
        start_time = time.time()

        # 首先筛选领域相关的页面
        domain_relevant_candidates = await self._filter_domain_relevant_pages(term,feature_id,commit_ids,page)

        
        self.logger.info(f"Filtered candidates to {len(domain_relevant_candidates)} "
                        f"domain relevant candidates for '{term}'")

        # 章节匹配，参考_find_matching_sections的逻辑
        section_candidates = []
        for candidate in domain_relevant_candidates:
            candidate.page = self.wiki.page(candidate.title)
            section_title,section_text,is_find = await self._find_matching_sections(candidate.page, term)
            section_candidates.append(LinkingCandidate(
                mention=term,
                title=section_title,
                url=candidate.url + ("#" + section_title if is_find else ''),
                summary=section_text
            ))
        
        self.logger.info(f"Found {len(section_candidates)} section candidates for '{term}'")
        
        # 只对领域相关的候选项进行详细的相关性检查
        batch_results = await self._batch_check_relevance(
            section_candidates, term, context
        )
        
        # 应用结果到候选项
        filtered_candidates = []
        for candidate, (is_match, confidence) in zip(domain_relevant_candidates, batch_results):
            if is_match:
                candidate.confidence = confidence
                filtered_candidates.append(candidate)
                
        elapsed_time = time.time() - start_time
        self.logger.info(f"Processed disambiguation for '{term}' in {elapsed_time:.2f}s. "
                        f"Found {len(filtered_candidates)} relevant matches from "
                        f"{len(domain_relevant_candidates)} domain relevant candidates.")
                        
        return filtered_candidates

    async def _batch_check_relevance(self, candidates: List[LinkingCandidate], 
                                term: str, context: str) -> List[Tuple[bool, float]]:
        """批量检查候选项与上下文的相关性
        
        通过一次LLM调用，批量检查多个候选项的相关性，提高效率。
        
        Args:
            candidates: 候选项列表
            term: 原始搜索词
            context: 上下文内容
            
        Returns:
            List[Tuple[bool, float]]: 每个候选项的(是否匹配,置信度)元组列表
        """
        BATCH_SIZE = 20
        results = []
        
        for i in range(0, len(candidates), BATCH_SIZE):
            batch = candidates[i:i+BATCH_SIZE]
            batch_results = await self._process_relevance_batch(batch, term, context)
            results.extend(batch_results)
            
        return results
        
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
                    3. 'disambiguation_source': whether the selected page was from a disambiguation resolution"
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


    # async def _select_valid_ngram_matches(self, mentions: list[str], context: str,
    #                                     ngram_candidates: List[LinkingCandidate]) -> List[LinkingCandidate]:
    #     """从n-grams候选中选择所有合理的匹配"""
    #     if not ngram_candidates:
    #         return []
        
    #     try:
    #         # Improved prompt formatting to ensure valid JSON response
    #         prompt = f"""Given mentions from Linux kernel documentation and their context, select appropriate pairs of (mention, Wikipedia page).
            
    #         Mentions: {json.dumps(mentions)}
    #         Context: {context}
    #         Candidates: {self._format_candidates(ngram_candidates)}
            
    #         Return a JSON array of matches in this exact format:
    #         [
    #             {{
    #                 "mention_index": <index of matching mention>,
    #                 "page_index": <index of matching page>,
    #                 "confidence": <score between 0 and 1>,
    #                 "reasoning": "<brief explanation>"
    #             }}
    #         ]
            
    #         Only include pairs where the mention and page describe the exact same concept."""
            
    #         response = await self._get_llm_response(prompt)
    #         if not response:
    #             return []
            
    #         # More robust JSON parsing
    #         try:
    #             # First try to find JSON array within the response
    #             json_start = response.find('[')
    #             json_end = response.rfind(']') + 1
    #             if json_start >= 0 and json_end > json_start:
    #                 cleaned_response = response[json_start:json_end]
    #             else:
    #                 cleaned_response = strip_json(response)
                
    #             results = json.loads(cleaned_response)
                
    #         except json.JSONDecodeError:
    #             self.logger.error(f"Failed to parse JSON response: {response}")
    #             return []
            
    #         valid_matches = []
            
    #         for result in results:
    #             if isinstance(result, dict) and 'mention_index' in result and 'page_index' in result:
    #                 if (0 <= result['mention_index'] < len(mentions) and 
    #                     0 <= result['page_index'] < len(ngram_candidates)):
                        
    #                     selected = ngram_candidates[result['page_index']]
    #                     selected.mention = mentions[result['mention_index']]
    #                     selected.confidence = result.get('confidence', 0.0)
    #                     valid_matches.append(selected)
                        
    #                     self.logger.info(f"Matched: {selected.mention} -> {selected.title} "
    #                                    f"(confidence: {selected.confidence})")
            
    #         return valid_matches
            
    #     except Exception as e:
    #         self.logger.error(f"Failed to select valid matches for {mentions}: {str(e)}")
    #         return []


    def _deduplicate_candidates(self, candidates: List[LinkingCandidate]) -> List[LinkingCandidate]:
        """去除重复的候选"""
        seen = set()
        unique_candidates = []
        
        for candidate in candidates:
            if candidate.title not in seen:
                seen.add(candidate.title)
                unique_candidates.append(candidate)
                
        return unique_candidates
        
    def _create_variation_prompt(self, mention: str, context: str) -> str:
        """创建生成变体的提示"""
        return f"""Please generate variations of the following technical term from Linux kernel documentation and relevant to the provided context. 
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
        Context: "{context}"
        Example response format for 'Virtual Memory':
        ["Virtual Memory", "VM","virt_mem"]
        Example response for "RCU":
        [ "RCU","Read-Copy-Update"]
        """
        
    def _parse_variations_response(self, response: str, mention: str) -> List[str]:
        """解析 LLM 响应"""
        try:
            cleaned_response = strip_json(response)
            variations = json.loads(cleaned_response)
            
            if isinstance(variations, list):
                # 使用集合去重，然后转回列表，保持顺序
                unique_variations = []
                seen = set()
                for v in variations:
                    if v and isinstance(v, str):
                        v_stripped = v.strip()
                        if v_stripped and v_stripped not in seen:
                            seen.add(v_stripped)
                            unique_variations.append(v_stripped)
                return unique_variations
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
        1. Does this Wikipedia page describe a concept that matches how the term is used in the Linux context?
        2. Check if the term is being used as a technical entity or just a common word/adjective:
           - If it's clearly just a common word (like "core" meaning "main" or "central") or a generic adjective with no technical meaning, it should NOT match.
           - If the page title contains the entity name but refers to a broader or different concept than what's being used in Linux, be cautious.
        3. For programming concepts, prefer the most specific match:
           - For example, "file" in kernel code could refer to either "Computer file" or "file system" depending on the context
        4. A partial match is acceptable if the Wikipedia page covers the concept, even if the title isn't an exact match.

        Return a JSON object with the following structure:
        {{
            "confidence": 0-1, // A value between 0 and 1 indicating how confident we are in the match, where 0 means no confidence and 1 means complete confidence
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

    async def _process_relevance_batch(self, candidates: List[LinkingCandidate], 
                                   term: str, context: str) -> List[Tuple[bool, float]]:
        """处理一批候选项的相关性检查
        
        Args:
            candidates: 候选项列表
            term: 原始搜索词
            context: 上下文内容
            
        Returns:
            List[Tuple[bool, float]]: 结果列表
        """
        if not candidates:
            return []
            
        # 构建批量处理的提示
        candidates_json = []
        for i, candidate in enumerate(candidates):
            candidates_json.append(
                json.dumps({
                    "index": i,
                    "title": candidate.title,
                    "summary": candidate.summary[:500]
                })
            )
            
        candidates_str = ",".join(candidates_json)
        
        prompt = f"""Given a term from Linux kernel documentation and its context, analyze which of these Wikipedia pages appropriately match the concept.

        Original term: {term}
        Context from documentation: {context[:300] if context else "No context provided"}

        Candidate Wikipedia pages (only first sentence of each summary shown):
        {candidates_str}

        For EACH candidate, determine if it matches the meaning of the term as used in the Linux context based on the title and first sentence.
        
        Return a JSON array where each element corresponds to a candidate and has this structure:
        [
            {{
                "index": 0,
                "is_match": true/false,
                "confidence": 0-1,
            }},
            // more results...
        ]
        """
        
        try:
            response = await self._get_llm_response(prompt)
            cleaned_response = strip_json(response)
            results = json.loads(cleaned_response)
            
            # 验证结果有效性并映射到元组列表
            match_results = []
            for result in results:
                if isinstance(result, dict) and "index" in result and "is_match" in result:
                    idx = result.get("index")
                    if 0 <= idx < len(candidates):
                        is_match = result.get("is_match", False)
                        confidence = result.get("confidence", 0.0)
                        match_results.append((is_match, confidence))
                    
            # 如果结果数量不匹配，补全结果
            if len(match_results) < len(candidates):
                for _ in range(len(candidates) - len(match_results)):
                    match_results.append((False, 0.0))
                    
            return match_results
            
        except Exception as e:
            self.logger.error(f"Batch relevance check failed: {e}")
            # 出错时返回所有不匹配
            return [(False, 0.0) for _ in candidates]

    def _check_page_exists_local(self, title: str) -> bool:
        """检查本地MediaWiki页面是否存在
        
        Args:
            title: 页面标题
            
        Returns:
            bool: 页面是否存在
        """
        try:
            api_url = self.local_wiki_api
            params = {
                'action': 'query',
                'format': 'json',
                'titles': title,
            }
            
            response = requests.get(api_url, params=params)
            data = response.json()
            
            if 'query' in data and 'pages' in data['query']:
                for page_id in data['query']['pages']:
                    # 如果页面ID为负数，则页面不存在
                    if int(page_id) < 0:
                        return False
                    else:
                        return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to check if page exists: {title}, error: {e}")
            return False

    def cleanup_and_report(self):
        """清理资源并生成最终报告"""
        self.logger.info("=== Entity Linking Session Summary ===")
        self.log_api_stats()
        
        # 计算成功率
        total_requests = self.api_stats['total_requests']
        successful_requests = total_requests - self.api_stats['failed_requests']
        success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0
        
        self.logger.info(f"Success rate: {success_rate:.2f}%")
        self.logger.info(f"Cache hit rate: {self.api_stats['cached_requests'] / max(total_requests, 1) * 100:.2f}%")
        
        if self.api_stats['rate_limited_requests'] > 0:
            self.logger.warning(f"Encountered {self.api_stats['rate_limited_requests']} rate limiting events")
            self.logger.info("Consider increasing delays between requests if rate limiting persists")
        
        self.logger.info("=== End Summary ===")
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        self.cleanup_and_report()