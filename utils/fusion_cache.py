import json
import os
from typing import List, Optional, Dict, Any
from functools import wraps
import logging

class FusionCache:
    def __init__(self, cache_file: str = "data/cache/fusion/fusion_cache_mm_0512.json"):
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

    def _get_cache_key(self, entity: str, feature_id: str, commit_ids: list) -> str:
        """统一的缓存键生成方法"""
        # 添加调试日志
        # print(f"Debug - commit_ids before processing: {commit_ids}")
        
        # 确保 commit_ids 是列表并且所有元素都是字符串
        if commit_ids is None:
            commit_ids = []  # 如果 commit_ids 为 None，则设定为空列表

        # 确保所有元素都是字符串，过滤掉空值，并排序以保证顺序一致
        commit_ids = sorted([str(cid) for cid in commit_ids if cid])  # 过滤掉空值并排序

        # 用下划线连接所有非空并排序后的 commit_ids
        commit_ids_str = '_'.join(commit_ids)  # 将列表中的元素用下划线连接成一个字符串

        # Debug 输出，查看最后生成的 commit_ids_str
        # print("Debug - final commit_ids_str:", commit_ids_str)  # 确保输出为字符串，不应为列表


        # 如果需要将结果进一步使用，可以返回或者继续处理 commit_ids_str
        
        feature_id_str = feature_id if feature_id else ''
        return f"{entity}_{feature_id_str}_{commit_ids_str}"

    def cache_operation(self, operation: str, cache_type: str, entity: str, 
                       feature_id: str, commit_ids: list, data: Any = None) -> Optional[Any]:
        """统一的缓存操作方法"""
        cache_key = self._get_cache_key(entity, feature_id, commit_ids)
        
        if operation == 'get':
            return self.caches[cache_type].get(cache_key)
        elif operation == 'set':
            self.caches[cache_type][cache_key] = data
            self._save_cache_file(cache_type)
        
        return None

    def get_reference(self, entity: str, feature_id: str, commit_ids: list) -> Optional[Dict]:
        return self.cache_operation('get', 'reference', entity, feature_id, commit_ids)

    def set_reference(self, entity: str, feature_id: str, commit_ids: list, reference_data: Dict) -> None:
        self.cache_operation('set', 'reference', entity, feature_id, commit_ids, reference_data)

    def get_fusion(self, entity: str, feature_id: str, commit_ids: list) -> Optional[Dict]:
        return self.cache_operation('get', 'fusion', entity, feature_id, commit_ids)

    def set_fusion(self, entity: str, feature_id: str, commit_ids: list, fusion_data: Dict) -> None:
        self.cache_operation('set', 'fusion', entity, feature_id, commit_ids, fusion_data)

    def cached_operation(cache_type: str):
        """缓存操作的装饰器"""
        def decorator(func):
            @wraps(func)
            async def wrapper(processor_instance, entity, feature_id=None, commit_ids=None, *args, **kwargs):
                logger = logging.getLogger('entity_processor')
                
                if not hasattr(processor_instance, 'fusion_cache'):
                    logger.error("EntityProcessor instance missing fusion_cache attribute")
                    try:
                        processor_instance.fusion_cache = FusionCache()
                        logger.info("Successfully created new FusionCache instance")
                    except Exception as e:
                        logger.error(f"Failed to create FusionCache: {e}")
                        return await func(processor_instance, entity, feature_id, commit_ids, *args, **kwargs)
                
                fusion_cache = processor_instance.fusion_cache
                
                # 如果没有提供缓存所需的参数，直接执行原函数
                if not all([entity, feature_id]):
                    return await func(processor_instance, entity, feature_id, commit_ids, *args, **kwargs)
                
                # 尝试从缓存获取
                try:
                    cached = fusion_cache.cache_operation('get', cache_type, entity.name, feature_id, commit_ids)
                    if cached is not None:
                        logger.info(f"Cache hit for {cache_type} of: {entity}")
                        return cached
                except Exception as e:
                    logger.error(f"Error accessing cache: {e}")
                    return await func(processor_instance, entity, feature_id, commit_ids, *args, **kwargs)
                
                # 缓存未命中，执行原函数
                result = await func(processor_instance, entity, feature_id, commit_ids, *args, **kwargs)
                
                # 缓存结果
                if result is not None:
                    try:
                        fusion_cache.cache_operation('set', cache_type, entity.name, feature_id, commit_ids, result)
                        logger.info(f"Cached {cache_type} result for: {entity}")
                    except Exception as e:
                        logger.error(f"Error saving to cache: {e}")
                
                return result
            return wrapper
        return decorator 