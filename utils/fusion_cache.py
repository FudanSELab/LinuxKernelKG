import json
import os
from typing import List, Optional, Dict, Any
from functools import wraps
import logging

class FusionCache:
    def __init__(self, cache_file: str = "data/cache/fusion_cache_131.json"):
        self.cache_file = cache_file
        self.cache_files = {
            'reference': self.cache_file,
            'fusion': self.cache_file.replace('.json', '_fusion.json'),
            'candidates': self.cache_file.replace('.json', '_candidates.json'),
        }
        self.caches = {
            'reference': self._load_cache_file('reference'),
            'fusion': self._load_cache_file('fusion'),
            'candidates': self._load_cache_file('candidates'),
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

    def _get_cache_key(self, entity: str, cache_type: str) -> str:
        """统一的缓存键生成方法，仅基于 entity 和 cache_type"""
        prefix = f"{cache_type}_" if cache_type != 'reference' else ""
        return f"{prefix}{entity}"

    def cache_operation(self, operation: str, cache_type: str, entity: str, data: Any = None) -> Optional[Any]:
        """统一的缓存操作方法，去除 feature_id 和 commit_ids"""
        cache_key = self._get_cache_key(entity, cache_type)

        if operation == 'get':
            return self.caches[cache_type].get(cache_key)
        elif operation == 'set':
            self.caches[cache_type][cache_key] = data
            self._save_cache_file(cache_type)

        return None

    def get_reference(self, entity: str) -> Optional[Dict]:
        return self.cache_operation('get', 'reference', entity)

    def set_reference(self, entity: str, reference_data: Dict) -> None:
        self.cache_operation('set', 'reference', entity, reference_data)

    def get_fusion(self, entity: str) -> Optional[Dict]:
        return self.cache_operation('get', 'fusion', entity)

    def set_fusion(self, entity: str, fusion_data: Dict) -> None:
        self.cache_operation('set', 'fusion', entity, fusion_data)

    def get_candidates(self, entity: str) -> Optional[List[str]]:
        return self.cache_operation('get', 'candidates', entity)

    def set_candidates(self, entity: str, candidates: List[str]) -> None:
        self.cache_operation('set', 'candidates', entity, candidates)

    @staticmethod
    def cached_operation(cache_type: str):
        """缓存操作的装饰器，去除 feature_id 和 commit_ids"""
        def decorator(func):
            @wraps(func)
            async def wrapper(processor_instance, entity, *args, **kwargs):
                logger = logging.getLogger('entity_fusion')

                if not hasattr(processor_instance, 'fusion_cache'):
                    logger.error("EntityFusion instance missing fusion_cache attribute")
                    try:
                        processor_instance.fusion_cache = FusionCache()
                        logger.info("Successfully created new FusionCache instance")
                    except Exception as e:
                        logger.error(f"Failed to create FusionCache: {e}")
                        return await func(processor_instance, entity, *args, **kwargs)

                fusion_cache = processor_instance.fusion_cache

                # 从缓存获取
                cached = fusion_cache.cache_operation('get', cache_type, entity)
                if cached is not None:
                    logger.info(f"Cache hit for {cache_type} of: {entity}")
                    return cached
                logger.info(f"Cache miss for {cache_type} of: {entity}")

                # 执行原函数
                result = await func(processor_instance, entity, *args, **kwargs)

                # 缓存结果
                if result is not None:
                    fusion_cache.cache_operation('set', cache_type, entity, result)
                    logger.info(f"Cached {cache_type} result for: {entity}")

                return result
            return wrapper
        return decorator