import json
import os
from dataclasses import asdict
from typing import List, Optional, Union, Dict
from models.linking import LinkingCandidate
from functools import wraps
import logging

class LinkCache:
    def __init__(self, cache_file: str = "data/cache/link_cache_deepseek_130.json"):
        self.cache_file = cache_file
        self.cache_files = {
            'main': self.cache_file,
            'variations': self.cache_file.replace('.json', '_variations.json'),
            'disambig': self.cache_file.replace('.json', '_disambig.json')
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

    def _get_cache_key(self, term: str, cache_type: str) -> str:
        """简化的缓存键生成方法，只基于 term 和 cache_type"""
        prefix = f"{cache_type}_" if cache_type != 'main' else ""
        return f"{prefix}{term}"

    def cache_operation(self, operation: str, cache_type: str, term: str, data: any = None) -> Optional[any]:
        """统一的缓存操作方法，去除 feature_id 和 commit_ids

        Args:
            operation: 'get' 或 'set'
            cache_type: 缓存类型 ('main', 'variations', 'disambig')
            term: 搜索词
            data: 要缓存的数据 (仅在 set 操作时需要)

        Returns:
            获取操作时返回缓存的数据，设置操作时返回 None
        """
        cache_key = self._get_cache_key(term, cache_type)

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
                self.caches[cache_type][cache_key] = data
            else:
                serialized_data = [self._serialize_candidate(item) for item in data]
                self.caches[cache_type][cache_key] = serialized_data
            self._save_cache_file(cache_type)

        return None

    # 简化后的公共接口方法，去除 feature_id 和 commit_ids
    def get(self, term: str) -> Optional[List[LinkingCandidate]]:
        return self.cache_operation('get', 'main', term)

    def set(self, term: str, candidates: List[LinkingCandidate]) -> None:
        self.cache_operation('set', 'main', term, candidates)

    def get_variations(self, term: str) -> Optional[List[str]]:
        return self.cache_operation('get', 'variations', term)

    def set_variations(self, term: str, variations: List[str]) -> None:
        self.cache_operation('set', 'variations', term, variations)

    def get_disambig_results(self, term: str) -> Optional[List[LinkingCandidate]]:
        return self.cache_operation('get', 'disambig', term)

    def set_disambig_results(self, term: str, candidates: List[LinkingCandidate]) -> None:
        self.cache_operation('set', 'disambig', term, candidates)

    # 保留序列化相关的辅助方法
    def _serialize_candidate(self, candidate: LinkingCandidate) -> dict:
        return asdict(candidate)

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
        """缓存操作的装饰器，简化参数传递

        Args:
            cache_type: 缓存类型 ('main', 'variations', 'disambig')

        Example:
            @LinkCache.cached_operation('variations')
            async def _generate_variations(self, mention):
                # 只需要实现实际的获取逻辑
                return await self._actual_get_variations(mention)
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(linker_instance, term, *args, **kwargs):
                logger = logging.getLogger('entity_linker')

                # 检查 linker_instance 是否正确初始化
                if not hasattr(linker_instance, 'link_cache'):
                    logger.error(f"EntityLinker instance missing link_cache attribute. Instance type: {type(linker_instance)}")
                    linker_instance.link_cache = LinkCache()
                    logger.info("Successfully created new LinkCache instance")

                link_cache = linker_instance.link_cache

                # 从缓存获取
                cached = link_cache.cache_operation('get', cache_type, term)
                if cached is not None:
                    logger.info(f"Cache hit for {cache_type} of: {term}")
                    return cached
                logger.info(f"Cache miss for {cache_type} of: {term}")

                # 缓存未命中，执行原函数
                result = await func(linker_instance, term, *args, **kwargs)

                # 缓存结果
                if result is not None:
                    link_cache.cache_operation('set', cache_type, term, result)
                    logger.info(f"Cached {cache_type} result for: {term}")

                return result
            return wrapper
        return decorator