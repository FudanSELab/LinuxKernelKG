from typing import Dict, List, Optional, Any, Set
import json
from datetime import datetime
import copy


class Entity:
    """
    Entity是知识图谱中的基本单元，表示Linux内核中的一个实体（组件、概念、类等）。
    实体可以通过多种方式创建：从文本提取、从外部链接、或通过融合。
    """

    # # 实体来源类型枚举
    # SOURCE_TYPES = {"wikipedia", "document", "code"}
    
    # 实体类别枚举
    ENTITY_TYPES = {
        "unknown"
    }

    def __init__(self,
                 name: str,
                 feature_id: int,
                 id: Optional[str] = None,
                 entity_type: str = "unknown",
                 context: str = "",
                #  source_type: str = "wikipedia",
                 description: str = "",
                 relationships: List[str] = None,
                 external_links: List[str] = None,
                 aliases: List[str] = None,
                 created_at: str = None,
                 updated_at: str = None,
                 properties: Dict[str, Any] = None):
        """
        初始化一个Entity对象
        
        Args:
            name: 实体名称
            id: 实体唯一标识符（可选，如果不提供将自动生成）
            entity_type: 实体类型
            feature_id: 关联的特性ID
            description: 实体描述
            aliases: 别名列表
            properties: 其他属性
            external_links: 外部链接列表
            relationships: 与其他实体的关系列表
            commit_ids: 关联的commit_ids列表
        """
        # 基本属性
        self.name = name
        self.id = id or f"entity_{hash(name)}_{hash(datetime.now().isoformat())}"
        
        # 验证实体类别
        if entity_type not in self.ENTITY_TYPES:
            entity_type = "unknown"
        self.entity_type = entity_type
        
        # # 验证来源类型
        # if source_type not in self.SOURCE_TYPES:
        #     source_type = "extraction"
        # self.source_type = source_type
        
        # 其他属性
        self.feature_id = feature_id
        self.description = description
        self.context = context
        self.aliases = aliases or []
        self.properties = properties or {}
        
        # 关系和链接数据
        self.relationships = []  # 与其他实体的关系
        self.commit_ids = []  # 关联的commit_ids
        self.external_links = []  # 外部知识库链接
        
        # 元数据
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
    
    def to_dict(self) -> Dict[str, Any]:
        """
        将Entity对象转换为字典
        
        Returns:
            Dict: 表示Entity的字典
        """
        return {
            "id": self.id,
            "name": self.name,
            "entity_type": self.entity_type,
            # "source_type": self.source_type,
            "feature_id": self.feature_id,
            "context": self.context,
            "description": self.description,
            "aliases": self.aliases,
            "properties": self.properties,
            "relationships": self.relationships,
            "external_links": self.external_links,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, entity_dict: Dict[str, Any]) -> 'Entity':
        """
        从字典创建Entity对象
        
        Args:
            entity_dict: 表示Entity的字典
        """
        return cls(**entity_dict)
    
    def to_json(self, indent: int = 2) -> str:
        """
        将Entity对象转换为JSON字符串
        
        Args:
            indent: JSON缩进级别
            
        Returns:
            str: JSON字符串
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
    
    # def add_feature_id(self, feature_id: int) -> None:
    #     """
    #     添加特性ID到实体
        
    #     Args:
    #         feature_id: 特性ID
    #     """
    #     if feature_id not in self.feature_id:
    #         self.feature_id = feature_id
    #         self.updated_at = datetime.now().isoformat()
    
    def set_context_by_feature_description(self, feature_description: str) -> None:
        """
        设置实体上下文
        
        Args:
            feature_description: 特性描述
        """
        self.context = f"feature_description: {feature_description}\n"

    def set_context(self,h1,h2,feature_description):
        """
        设置实体上下文，根据传入的h1、h2和feature_description
        
        Args:
            h1: 一级标题
            h2: 二级标题
            feature_description: 特性描述
        """
        context_parts = []
        
        if h1 is not None and h1 != '':
            context_parts.append(f"h1: {h1}")
        
        if h2 is not None and h2 != '':
            context_parts.append(f"h2: {h2}")
        if feature_description is not None:
            context_parts.append(f"feature_description: {feature_description}")
        
        if context_parts:
            self.context = "\n".join(context_parts)
            self.updated_at = datetime.now().isoformat()

    def add_alias(self, alias: str) -> None:
        """
        添加别名到实体
        
        Args:
            alias: this内项别名
        """
        if alias not in self.aliases:
            self.aliases.append(alias)
            self.updated_at = datetime.now().isoformat()
    
    def add_external_link(self, url_type: str, url: str | List[str]) -> None:
        """
        添加外部链接到实体
        
        Args:
            url_type: 链接类型 (如 'wikipedia', 'wikidata')
            url: 链接URL列表
        """
        # 检查是否已存在相同类型的链接
        existing_link = None
        for link in self.external_links:
            if link.get("url_type") == url_type:
                existing_link = link
                break
                
        if existing_link:
            # 已存在相同类型的链接，添加到现有条目
            urls = existing_link.get("url", [])
            if isinstance(url, str):
                if url not in urls:
                    urls.append(url)
            else:
                for u in url:
                    if u not in urls:
                        urls.append(u)
            existing_link["url"] = urls
        else:
            # 创建新的链接条目
            urls = [url] if isinstance(url, str) else url
            self.external_links.append({"url_type": url_type, "url": urls})
        
        self.updated_at = datetime.now().isoformat()
    
    # def add_relationship(self, target_entity_id: str, relation_type: str, 
    #                     properties: Dict[str, Any] = None, confidence: float = 1.0) -> None:
    #     """
    #     添加与另一个实体的关系
        
    #     Args:
    #         target_entity_id: 目标实体ID
    #         relation_type: 关系类型
    #         properties: 关系属性
    #         confidence: 关系置信度
    #     """
    #     self.relationships.append({
    #         "target_entity_id": target_entity_id,
    #         "relation_type": relation_type,
    #         "properties": properties or {},
    #         "confidence": confidence,
    #         "created_at": datetime.now().isoformat()
    #     })
    #     self.updated_at = datetime.now().isoformat()
    
    def set_confidence_score(self, score: float) -> None:
        """
        设置实体置信度分数
        
        Args:
            score: 置信度分数 (0.0-1.0)
        """
        self.confidence_score = max(0.0, min(1.0, score))  # 确保在0-1范围内
        self.updated_at = datetime.now().isoformat()
    
    # 判断两个实体wikipedia的链接是否相同
    def is_same_wikipedia_link(self, other_entity: 'Entity') -> bool:
        """
        判断两个实体的Wikipedia链接是否相同
        
        Args:
            other_entity: 要比较的实体
            
        Returns:
            bool: 是否为同一实体
        """
        for link in self.external_links:
            if link['url_type'] == 'wikipedia':
                for other_link in other_entity.external_links:
                    if other_link['url_type'] == 'wikipedia':
                        # 检查两个URL列表是否有交集
                        for url in link['url']:
                            if url in other_link['url']:
                                return True
        return False
    

    def merge_with(self, other_entity: 'Entity') -> None:
        """
        与另一个实体合并
        
        Args:
            other_entity: 要合并的实体
        """
        # 合并基本属性
        if not self.description and other_entity.description:
            self.description = other_entity.description
            
        # # 合并特性ID
        # if other_entity.feature_id not in self.feature_id:
        #     self.feature_id = other_entity.feature_id
            
        for alias in other_entity.aliases:
            self.add_alias(alias)
            
        # 添加其他实体的名称为别名（如果不同）
        if other_entity.name != self.name:
            self.add_alias(other_entity.name)
            
        # 合并外部链接
        # 创建url_type到url集合的映射
        existing_links = {}
        for link in self.external_links:
            url_type = link["url_type"]
            urls = link["url"]
            if url_type not in existing_links:
                existing_links[url_type] = set()
            # 将列表中的每个URL添加到集合中
            for url in urls:
                existing_links[url_type].add(url)
        
        # 合并other_entity的链接
        for link in other_entity.external_links:
            url_type = link["url_type"]
            urls = link["url"]
            if url_type not in existing_links:
                existing_links[url_type] = set()
                self.external_links.append(link)
            else:
                # 检查每个URL是否已存在
                has_new_url = False
                for url in urls:
                    if url not in existing_links[url_type]:
                        existing_links[url_type].add(url)
                        has_new_url = True
                if has_new_url:
                    self.external_links.append(link)
        
        # # 合并关系
        # for rel in other_entity.relationships:
        #     if rel not in self.relationships:
        #         self.relationships.append(rel)
                
        # 合并属性
        for key, value in other_entity.properties.items():
            if key not in self.properties:
                self.properties[key] = value
                
        self.updated_at = datetime.now().isoformat()
    
    def is_same_entity(self, other_entity: 'Entity') -> bool:
        """
        判断是否为同一实体（基于名称和别名）
        
        Args:
            other_entity: 要比较的实体
            
        Returns:
            bool: 是否为同一实体
        """
        # 如果名称相同，直接返回True
        if self.name.lower() == other_entity.name.lower():
            return True
            
        # 检查此实体的名称是否在其他实体的别名中
        if self.name.lower() in [alias.lower() for alias in other_entity.aliases]:
            return True
            
        # 检查其他实体的名称是否在此实体的别名中
        if other_entity.name.lower() in [alias.lower() for alias in self.aliases]:
            return True
            
        # 检查别名是否有交集
        self_aliases = set(alias.lower() for alias in self.aliases)
        other_aliases = set(alias.lower() for alias in other_entity.aliases)
        if self_aliases.intersection(other_aliases):
            return True
            
        return False

    def clone(self) -> 'Entity':
        """Creates a deep copy of this entity instance."""
        return copy.deepcopy(self)
