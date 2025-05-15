import json
import os
from dataclasses import asdict
from typing import List, Optional, Union, Dict
from models.linking import LinkingCandidate
from functools import wraps
import logging

class LinkCache:
    def __init__(self, cache_file: str = "data/cache/link_cache_deepseek_online.json"):
        self.cache_file = cache_file
        self.cache_files = {
            # 'main': self.cache_file.replace('.json','_main.json'),
            'main': self.cache_file,
            'variations': self.cache_file.replace('.json', '_0506_variations.json'),
            'disambig': self.cache_file.replace('.json', '_0506_disambig.json')
        }
        self.caches = {
            'main': self._load_cache_file('main'),
            'variations': self._load_cache_file('variations'),
            'disambig': self._load_cache_file('disambig')
        }

    def _load_cache_file(self, cache_type: str) -> dict:
        """统一的缓存文件加载方法"""
        try:
            if os.path.exists(self.cache_files[cache_type]):
                with open(self.cache_files[cache_type], 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading {cache_type} cache file: {e}")
        return {}

    def _save_cache_file(self, cache_type: str) -> None:
        """统一的缓存文件保存方法"""
        try:
            os.makedirs(os.path.dirname(self.cache_files[cache_type]), exist_ok=True)
            with open(self.cache_files[cache_type], 'w', encoding='utf-8') as f:
                json.dump(self.caches[cache_type], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving {cache_type} cache file: {e}")

    def _get_cache_key(self, term: str, feature_id: str, commit_ids: list, cache_type: str) -> str:
        """统一的缓存键生成方法，确保键的唯一性"""
        # 规范化参数以减少重复键的可能性
        normalized_term = term.lower().strip()
        
        # 确保commit_ids是有序的以生成一致的键
        commit_ids_str = '_'.join(sorted(commit_ids)) if commit_ids else "no_commits"
        
        # 为不同类型的缓存添加前缀
        prefix = f"{cache_type}_" if cache_type != 'main' else ""
        
        return f"{prefix}{normalized_term}_{feature_id}_{commit_ids_str}"

    def cache_operation(self, operation: str, cache_type: str, term: str, feature_id: str, 
                       commit_ids: list, data: any = None) -> Optional[any]:
        """统一的缓存操作方法
        
        Args:
            operation: 'get' 或 'set'
            cache_type: 缓存类型 ('main', 'variations', 'disambig')
            term: 搜索词
            feature_id: 特征ID
            commit_ids: 提交ID列表
            data: 要缓存的数据 (仅在 set 操作时需要)
            
        Returns:
            获取操作时返回缓存的数据，设置操作时返回 None
        """
        # 先不考虑语义信息
        # cache_key = self._get_cache_key(term, feature_id, commit_ids, cache_type)
        cache_key = term
        if operation == 'get':
            cached = self.caches[cache_type].get(cache_key)
            if not cached:
                return cached
                
            if cache_type == 'variations':
                return cached
            else:
                try:
                    return [self._deserialize_candidate(item, term) for item in cached]
                except Exception as e:
                    print(f"Error deserializing {cache_type} cache for {term}: {e}")
                    return None
                    
        elif operation == 'set':
            if cache_type == 'variations':
                # 检查是否已有缓存数据
                existing_variations = self.caches[cache_type].get(cache_key, [])
                
                # 合并新旧变体并去重
                if existing_variations:
                    # 将新变体与现有变体合并并去重
                    combined_variations = list(set(existing_variations + data))
                    self.caches[cache_type][cache_key] = combined_variations
                else:
                    # 确保新添加的变体不包含重复项
                    self.caches[cache_type][cache_key] = list(set(data))
            else:
                serialized_data = [self._serialize_candidate(item) for item in data]
                self.caches[cache_type][cache_key] = serialized_data
            self._save_cache_file(cache_type)
            
        return None

    # 简化后的公共接口方法
    def get(self, term: str, feature_id: str, commit_ids: list) -> Optional[List[LinkingCandidate]]:
        return self.cache_operation('get', 'main', term, feature_id, commit_ids)

    def set(self, term: str, feature_id: str, commit_ids: list, candidates: List[LinkingCandidate]) -> None:
        self.cache_operation('set', 'main', term, feature_id, commit_ids, candidates)

    def get_variations(self, term: str, feature_id: str, commit_ids: list) -> Optional[List[str]]:
        return self.cache_operation('get', 'variations', term, feature_id, commit_ids)

    def set_variations(self, term: str, feature_id: str, commit_ids: list, variations: List[str]) -> None:
        # 获取缓存键
        cache_key = self._get_cache_key(term, feature_id, commit_ids, 'variations')
        
        # 检查是否已有缓存数据
        existing_variations = self.caches['variations'].get(cache_key, [])
        
        # 合并新旧变体并去重
        if existing_variations:
            # 将新变体与现有变体合并并去重
            combined_variations = list(set(existing_variations + variations))
            self.caches['variations'][cache_key] = combined_variations
        else:
            # 确保新添加的变体不包含重复项
            self.caches['variations'][cache_key] = list(set(variations))
            
        # 保存更新后的缓存
        self._save_cache_file('variations')

    def get_disambig_results(self, term: str, feature_id: str, commit_ids: list) -> Optional[List[LinkingCandidate]]:
        return self.cache_operation('get', 'disambig', term, feature_id, commit_ids)

    def set_disambig_results(self, term: str, feature_id: str, commit_ids: list, candidates: List[LinkingCandidate]) -> None:
        self.cache_operation('set', 'disambig', term, feature_id, commit_ids, candidates)

    # 保留序列化相关的辅助方法
    def _serialize_candidate(self, candidate: LinkingCandidate) -> dict:
        return candidate.to_dict()

    def _deserialize_candidate(self, data: dict, term: str) -> LinkingCandidate:
        return LinkingCandidate(
            mention=data.get('mention', term),
            title=data.get('title', ''),
            url=data.get('url', ''),
            summary=data.get('summary', ''),
            confidence=data.get('confidence', 0.0),
            is_disambiguation=data.get('is_disambiguation', False)
        )

    @staticmethod
    def cached_operation(cache_type: str):
        """缓存操作的装饰器
        
        Args:
            cache_type: 缓存类型 ('main', 'variations', 'disambig')
            
        Example:
            @LinkCache.cached_operation('variations')
            async def get_variations(self, mention, feature_id, commit_ids):
                # 只需要实现实际的获取逻辑
                return await self._actual_get_variations(mention)
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(linker_instance, term, feature_id=None, commit_ids=None, *args, **kwargs):
                logger = logging.getLogger('entity_linker')
                
                # 添加更详细的日志
                logger.debug(f"Checking cache for term: {term}, feature_id: {feature_id}, cache_type: {cache_type}")
                logger.debug(f"Linker instance attributes: {dir(linker_instance)}")
                
                # 检查 linker_instance 是否正确初始化
                if not hasattr(linker_instance, 'link_cache'):
                    logger.error(f"EntityLinker instance missing link_cache attribute. Instance type: {type(linker_instance)}")
                    logger.error(f"Available attributes: {dir(linker_instance)}")
                    # 尝试初始化 link_cache
                    try:
                        linker_instance.link_cache = LinkCache()
                        logger.info("Successfully created new LinkCache instance")
                    except Exception as e:
                        logger.error(f"Failed to create LinkCache: {e}")
                        return await func(linker_instance, term, feature_id, commit_ids, *args, **kwargs)
                
                link_cache = linker_instance.link_cache
                
                # 如果没有提供缓存所需的参数，直接执行原函数
                # if not (feature_id and commit_ids):
                if not feature_id:
                    logger.warning(f"Missing required cache parameters - feature_id: {feature_id}, commit_ids: {commit_ids}")
                    return await func(linker_instance, term, feature_id, commit_ids, *args, **kwargs)
                
                # 确保commit_ids是列表类型
                if commit_ids is None:
                    commit_ids = []
                elif not isinstance(commit_ids, list):
                    # 处理非列表类型的commit_ids
                    if isinstance(commit_ids, str):
                        commit_ids = [commit_ids]
                    else:
                        try:
                            # 尝试转换为字符串后放入列表
                            commit_ids = [str(commit_ids)]
                        except Exception as e:
                            logger.error(f"Cannot convert commit_ids to list: {e}")
                            commit_ids = []
                
                # 尝试从缓存获取
                try:
                    cached = link_cache.cache_operation('get', cache_type, term, feature_id, commit_ids)
                    if cached is not None:
                        logger.info(f"Cache hit for {cache_type} of: {term}")
                        return cached
                    logger.info(f"Cache miss for {cache_type} of: {term}")
                except Exception as e:
                    logger.error(f"Error accessing cache: {e}")
                    return await func(linker_instance, term, feature_id, commit_ids, *args, **kwargs)
                
                # 缓存未命中，执行原函数
                result = await func(linker_instance, term, feature_id, commit_ids, *args, **kwargs)
                
                # 缓存结果
                if result is not None:
                    try:
                        link_cache.cache_operation('set', cache_type, term, feature_id, commit_ids, result)
                        logger.info(f"Cached {cache_type} result for: {term}")
                    except Exception as e:
                        logger.error(f"Error saving to cache: {e}")
                else:
                    logger.debug(f"No result to cache for {term}")
                
                return result
            return wrapper
        return decorator