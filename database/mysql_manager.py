#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
MySQL Database Manager

This module provides MySQL database connection management and entity-related
database operations for the Linux Kernel Knowledge Graph project.
"""

import pymysql
import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager
from datetime import datetime
from models.entity import Entity
from utils.logger import setup_logger

logger = setup_logger('mysql_manager', file_output=True)

class MySQLManager:
    """MySQL数据库管理器"""
    
    def __init__(self, config):
        """
        初始化MySQL管理器
        
        Args:
            config: 包含数据库配置的对象
        """
        self.config = config.DB_CONFIG
        self.logger = logger
        
    def get_connection(self):
        """获取数据库连接"""
        try:
            connection = pymysql.connect(
                host=self.config['host'],
                port=self.config['port'],
                user=self.config['user'],
                password=self.config['password'],
                database=self.config['database'],
                charset=self.config['charset'],
                autocommit=False,
                cursorclass=pymysql.cursors.DictCursor
            )
            return connection
        except Exception as e:
            self.logger.error(f"Failed to connect to MySQL: {e}")
            raise
    
    @contextmanager
    def get_db_connection(self):
        """数据库连接上下文管理器"""
        connection = None
        try:
            connection = self.get_connection()
            yield connection
        except Exception as e:
            if connection:
                connection.rollback()
            self.logger.error(f"Database operation failed: {e}")
            raise
        finally:
            if connection:
                connection.close()
    
    def insert_entity(self, entity: Entity) -> Optional[int]:
        """
        插入实体到数据库
        
        Args:
            entity: Entity对象
            
        Returns:
            Optional[int]: 插入的实体ID，如果失败返回None
        """
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                # 准备实体数据
                entity_data = self._prepare_entity_data(entity)
                
                # 检查是否已存在相同的实体 (name_en + feature_id)
                check_sql = """
                    SELECT eid FROM entities_extraction 
                    WHERE name_en = %s AND feature_id = %s
                """
                cursor.execute(check_sql, (entity_data['name_en'], entity_data['feature_id']))
                existing = cursor.fetchone()
                
                if existing:
                    self.logger.info(f"Entity already exists: {entity_data['name_en']} (feature_id: {entity_data['feature_id']})")
                    return existing['eid']
                
                # 插入新实体
                insert_sql = """
                    INSERT INTO entities_extraction 
                    (name_en, name_cn, source, definition_en, definition_cn, 
                     aliases, rel_desc, wikidata_id, feature_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_sql, (
                    entity_data['name_en'],
                    entity_data['name_cn'],
                    entity_data['source'],
                    entity_data['definition_en'],
                    entity_data['definition_cn'],
                    entity_data['aliases'],
                    entity_data['rel_desc'],
                    entity_data['wikidata_id'],
                    entity_data['feature_id']
                ))
                
                eid = cursor.lastrowid
                conn.commit()
                
                # 处理别名
                if entity.aliases:
                    self._insert_aliases(conn, eid, entity.aliases)
                
                self.logger.info(f"Successfully inserted entity: {entity.name} with eid: {eid}")
                return eid
                
        except Exception as e:
            self.logger.error(f"Failed to insert entity {entity.name}: {e}")
            return None
    
    def insert_entities_batch(self, entities: List[Entity]) -> List[Tuple[Entity, Optional[int]]]:
        """
        批量插入实体
        
        Args:
            entities: Entity对象列表
            
        Returns:
            List[Tuple[Entity, Optional[int]]]: (实体, 实体ID)的元组列表
        """
        results = []
        
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                for entity in entities:
                    try:
                        # 准备实体数据
                        entity_data = self._prepare_entity_data(entity)
                        
                        # 检查是否已存在
                        check_sql = """
                            SELECT eid, source FROM entities_extraction 
                            WHERE name_en = %s AND feature_id = %s
                        """
                        cursor.execute(check_sql, (entity_data['name_en'], entity_data['feature_id']))
                        existing = cursor.fetchone()
                        
                        if existing:
                            eid = existing['eid']
                            current_source = existing['source']
                            new_source = entity_data['source']
                            
                            # 如果新的source不为空且与当前source不同，则更新
                            print(f"current_source: {current_source}, new_source: {new_source}")
                            if new_source and new_source != current_source:
                                update_sql = """
                                    UPDATE entities_extraction 
                                    SET source = %s 
                                    WHERE eid = %s
                                """
                                cursor.execute(update_sql, (new_source, eid))
                                self.logger.info(f"Updated source for entity: {entity_data['name_en']} (eid: {eid})")
                            else:
                                self.logger.info(f"Entity already exists with same or empty source: {entity_data['name_en']} (eid: {eid})")
                            
                            results.append((entity, eid))
                            continue
                        
                        # 插入新实体
                        insert_sql = """
                            INSERT INTO entities_extraction 
                            (name_en, name_cn, source, definition_en, definition_cn, 
                             aliases, rel_desc, wikidata_id, feature_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        
                        cursor.execute(insert_sql, (
                            entity_data['name_en'],
                            entity_data['name_cn'],
                            entity_data['source'],
                            entity_data['definition_en'],
                            entity_data['definition_cn'],
                            entity_data['aliases'],
                            entity_data['rel_desc'],
                            entity_data['wikidata_id'],
                            entity_data['feature_id']
                        ))
                        
                        eid = cursor.lastrowid
                        
                        # 处理别名
                        if entity.aliases:
                            self._insert_aliases(conn, eid, entity.aliases)
                        
                        results.append((entity, eid))
                        self.logger.info(f"Successfully inserted entity: {entity.name} with eid: {eid}")
                        
                    except Exception as e:
                        self.logger.error(f"Failed to insert entity {entity.name}: {e}")
                        results.append((entity, None))
                
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"Batch insert failed: {e}")
            
        return results
    
    def _prepare_entity_data(self, entity: Entity) -> Dict[str, Any]:
        """
        准备实体数据用于数据库插入
        
        Args:
            entity: Entity对象
            
        Returns:
            Dict[str, Any]: 准备好的数据字典
        """
        # 从外部链接中提取Wikipedia URL作为source
        source = None
        wikidata_id = None
        
        for link in entity.external_links:
            if link.get('url_type') == 'wikipedia' and link.get('url'):
                urls = link['url']
                if isinstance(urls, list) and urls:
                    source = urls[0]
                elif isinstance(urls, str):
                    source = urls
                break
        
        # 准备别名JSON
        aliases_json = None
        if entity.aliases:
            aliases_list = []
            for alias in entity.aliases:
                aliases_list.append({
                    "name_en": alias,
                    "name_cn": "",
                    "source": ""
                })
            aliases_json = json.dumps(aliases_list, ensure_ascii=False)
        
        # 准备相关描述JSON
        rel_desc_json = None
        if entity.context:
            rel_desc_list = [{
                "desc_en": entity.context,
                "desc_cn": "",
                "source": "feature_description"
            }]
            rel_desc_json = json.dumps(rel_desc_list, ensure_ascii=False)
        
        return {
            'name_en': entity.name,
            'name_cn': '',  # 暂时为空，后续可以扩展
            'source': source,
            'definition_en': entity.description,
            'definition_cn': '',  # 暂时为空，后续可以扩展
            'aliases': aliases_json,
            'rel_desc': rel_desc_json,
            'wikidata_id': wikidata_id,
            'feature_id': entity.feature_id
        }
    
    def _insert_aliases(self, conn, eid: int, aliases: List[str]):
        """
        插入实体别名
        
        Args:
            conn: 数据库连接
            eid: 实体ID
            aliases: 别名列表
        """
        try:
            cursor = conn.cursor()
            
            for alias in aliases:
                # 检查别名是否已存在
                check_sql = """
                    SELECT alias_id FROM entity_aliases 
                    WHERE eid = %s AND name_en = %s
                """
                cursor.execute(check_sql, (eid, alias))
                existing = cursor.fetchone()
                
                if not existing:
                    insert_sql = """
                        INSERT INTO entity_aliases (eid, name_en, name_cn, source)
                        VALUES (%s, %s, %s, %s)
                    """
                    cursor.execute(insert_sql, (eid, alias, '', ''))
                    self.logger.info(f"Inserted alias: {alias} for entity eid: {eid}")
                
        except Exception as e:
            self.logger.error(f"Failed to insert aliases for eid {eid}: {e}")
    
    def get_last_processed_feature_id(self) -> Optional[int]:
        """
        获取最后处理的feature_id
        
        Returns:
            Optional[int]: 最后处理的feature_id，如果没有记录返回None
        """
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                sql = "SELECT MIN(feature_id) as min_feature_id FROM entities_extraction"
                cursor.execute(sql)
                result = cursor.fetchone()
                
                if result and result['min_feature_id'] is not None:
                    return result['min_feature_id']
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to get last processed feature_id: {e}")
            return None
    
    def get_entity_count_by_feature_id(self, feature_id: int) -> int:
        """
        获取指定feature_id的实体数量
        
        Args:
            feature_id: 特征ID
            
        Returns:
            int: 实体数量
        """
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                sql = "SELECT COUNT(*) as count FROM entities_extraction WHERE feature_id = %s"
                cursor.execute(sql, (feature_id,))
                result = cursor.fetchone()
                
                return result['count'] if result else 0
                
        except Exception as e:
            self.logger.error(f"Failed to get entity count for feature_id {feature_id}: {e}")
            return 0
    
    def test_connection(self) -> bool:
        """
        测试数据库连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                self.logger.info("Database connection test successful")
                return True
        except Exception as e:
            self.logger.error(f"Database connection test failed: {e}")
            return False 