import json
import os
from dataclasses import asdict
from typing import List, Optional, Union, Dict
from models.linking import LinkingCandidate

class LinkCache:
    def __init__(self, cache_file: str = "data/cache/link_cache.json"):
        self.cache_file = cache_file
        self.cache = self._load_cache()  # 初始化时从文件加载缓存

    def _load_cache(self) -> dict:
        """从文件加载缓存数据"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading cache file: {e}")
        return {}

    def _save_cache(self) -> None:
        """将缓存数据保存到文件"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving cache file: {e}")

    def _serialize_candidate(self, candidate: LinkingCandidate) -> dict:
        """将 LinkingCandidate 对象序列化为字典"""
        return asdict(candidate)

    def _deserialize_candidate(self, data: dict, term: str) -> LinkingCandidate:
        """将字典反序列化为 LinkingCandidate 对象"""
        return LinkingCandidate(
            mention=data.get('mention', term),
            title=data.get('title', ''),
            url=data.get('url', ''),
            summary=data.get('summary', ''),
            confidence=data.get('confidence', 0.0),
            is_disambiguation=data.get('is_disambiguation', False)
        )

    def get(self, term: str, feature_id: str, commit_ids: list) -> Optional[List[LinkingCandidate]]:
        """获取缓存的结果并转换为 LinkingCandidate 对象"""
        cache_key = self._make_key(term, feature_id, commit_ids)
        cached = self.cache.get(cache_key)
        
        if not cached:
            return None

        try:
            if isinstance(cached, list):
                return [
                    self._deserialize_candidate(item, term)
                    for item in cached
                    if isinstance(item, dict)
                ]
            elif isinstance(cached, dict) and 'result' in cached:
                return [
                    self._deserialize_candidate(item, term)
                    for item in cached['result']
                    if isinstance(item, dict)
                ]
            return None
        except Exception as e:
            print(f"Error deserializing cache for {term}: {e}")
            return None

    def set(self, term: str, feature_id: str, commit_ids: list, candidates: List[LinkingCandidate]) -> None:
        """将 LinkingCandidate 对象列表序列化后存入缓存并保存到文件"""
        cache_key = self._make_key(term, feature_id, commit_ids)
        serialized_candidates = [
            self._serialize_candidate(candidate)
            for candidate in candidates
        ]
        self.cache[cache_key] = serialized_candidates
        self._save_cache()  # 每次设置缓存后保存到文件

    def _make_key(self, term: str, feature_id: str, commit_ids: list) -> str:
        """生成缓存键"""
        commit_str = '_'.join(sorted(commit_ids)) if commit_ids else ''
        return f"{term}:{feature_id}:{commit_str}"