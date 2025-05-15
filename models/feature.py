from typing import List, Dict, Optional, Any
import json
from datetime import datetime


class Feature:
    """
    Feature是整个知识图谱pipeline的核心数据模型，代表Linux内核中的一个功能特性。
    此模型贯穿整个pipeline的各个阶段，从数据收集到知识图谱构建。
    """

    def __init__(self, 
                 feature_id: int = None, 
                 h1: str = "", 
                 h2: str = "", 
                 feature_description: str = "", 
                 version: str = "",
                 commit_ids: List[str] = None):
        """
        初始化一个Feature对象
        
        Args:
            feature_id: 特性的唯一标识符
            h1: 一级标题
            h2: 二级标题
            feature_description: 特性描述
            version: 版本信息
            commit_ids: 与此特性相关的提交ID列表
        """
        self.feature_id = feature_id
        self.h1 = h1
        self.h2 = h2
        self.feature_description = feature_description
        self.version = version
        self.commit_ids = commit_ids or []
        
        # 提取和处理阶段的数据
        self.commits = []  # 存储完整提交信息
        self.entities = []  # 存储提取的实体 (Entity对象列表)
        self.triples = []  # 存储提取的三元组关系
        
        # 实体链接和融合阶段的数据
        self.linked_entities = []  # 存储链接到外部知识库的实体
        self.fused_entities = []  # 存储经过融合处理的实体
        
        # 质量监控和指标数据
        self.quality_scores = {}  # 存储各阶段的质量评分
        self.metrics = {}  # 存储处理指标，如处理时间、置信度等
        
        # # 处理状态跟踪
        # self.processing_status = {
        #     "collector_completed": False,
        #     "enhancer_completed": False,
        #     "extractor_completed": False,
        #     "linker_completed": False,
        #     "fusioner_completed": False,
        #     "kg_builder_completed": False,
        # }
        self.last_updated = datetime.now().isoformat()
    
    # @classmethod
    # def from_dict(cls, data: Dict[str, Any]) -> 'Feature':
    #     """
    #     从字典创建Feature对象
        
    #     Args:
    #         data: 包含特性信息的字典
            
    #     Returns:
    #         Feature: 新创建的Feature对象
    #     """
    #     feature = cls(
    #         feature_id=data.get('feature_id'),
    #         h1=data.get('h1', ''),
    #         h2=data.get('h2', ''),
    #         feature_description=data.get('feature_description', ''),
    #         version=data.get('version', ''),
    #         commit_ids=data.get('commit_ids', [])
    #     )
        
    #     # 复制其他可用字段
    #     if 'entities' in data:
    #         feature.entities = data['entities']
    #     if 'triples' in data:
    #         feature.triples = data['triples']
    #     if 'commits' in data:
    #         feature.commits = data['commits']
    #     if 'linked_entities' in data:
    #         feature.linked_entities = data['linked_entities']
    #     if 'fused_entities' in data:
    #         feature.fused_entities = data['fused_entities']
            
    #     feature.last_updated = datetime.now().isoformat()
    #     return feature
    

    def to_dict(self) -> Dict[str, Any]:
        """
        将Feature对象转换为字典
        
        Returns:
            Dict: 表示Feature的字典
        """
        return {
            "feature_id": self.feature_id,
            "h1": self.h1,
            "h2": self.h2,
            "feature_description": self.feature_description,
            "version": self.version,
            "commit_ids": self.commit_ids,
            "entities": self.entities,
            "triples": self.triples,
            "commits": self.commits,
            "linked_entities": self.linked_entities,
            "fused_entities": self.fused_entities,
            "quality_scores": self.quality_scores,
            "metrics": self.metrics,
            # "processing_status": self.processing_status,
            "last_updated": self.last_updated
        }
    
    def to_json(self, indent: int = 2) -> str:
        """
        将Feature对象转换为JSON字符串
        
        Args:
            indent: JSON缩进级别
            
        Returns:
            str: JSON字符串
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
    
    # def update_status(self, stage_name: str, completed: bool = True) -> None:
    #     """
    #     更新处理状态
        
    #     Args:
    #         stage_name: 处理阶段名称
    #         completed: 是否已完成
    #     """
    #     status_key = f"{stage_name}_completed"
    #     if status_key in self.processing_status:
    #         self.processing_status[status_key] = completed
    #         self.last_updated = datetime.now().isoformat()
     
    def add_entity(self, entity: Dict[str, Any]) -> None:
        """
        添加实体到Feature
        
        Args:
            entity: 实体信息字典
        """
        self.entities.append(entity)
        self.last_updated = datetime.now().isoformat()
    
    def add_triple(self, head: str, relation: str, tail: str) -> None:
        """
        添加三元组关系到Feature
        
        Args:
            head: 头实体
            relation: 关系
            tail: 尾实体
        """
        self.triples.append([head, relation, tail])
        self.last_updated = datetime.now().isoformat()
    
    def add_linked_entity(self, entity: Dict[str, Any], matches: List[Dict[str, Any]]) -> None:
        """
        添加链接实体到Feature
        
        Args:
            entity: 原始实体
            matches: 匹配的外部实体列表
        """
        self.linked_entities.append({
            "entity": entity,
            "matches": matches
        })
        self.last_updated = datetime.now().isoformat()
    
    def add_fused_entity(self, canonical_form: str, variations: List[str], 
                         entity_class: str = "", reference: Dict[str, Any] = None) -> None:
        """
        添加融合实体到Feature
        
        Args:
            canonical_form: 规范形式
            variations: 变体形式列表
            entity_class: 实体类别
            reference: 参考信息
        """
        self.fused_entities.append({
            "canonical_form": canonical_form,
            "variations": variations,
            "class": entity_class,
            "reference": reference or {}
        })
        self.last_updated = datetime.now().isoformat()
    
    def set_quality_score(self, stage: str, score: float) -> None:
        """
        设置质量评分
        
        Args:
            stage: 处理阶段
            score: 质量分数
        """
        self.quality_scores[stage] = score
        self.last_updated = datetime.now().isoformat()
    
    def set_metric(self, name: str, value: Any) -> None:
        """
        设置处理指标
        
        Args:
            name: 指标名称
            value: 指标值
        """
        self.metrics[name] = value
        self.last_updated = datetime.now().isoformat()
    
    def is_completed(self) -> bool:
        """
        检查是否完成所有处理阶段
        
        Returns:
            bool: 是否完成所有阶段
        """
        return all(self.processing_status.values())
