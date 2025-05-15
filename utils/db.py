import pymysql
import json
from models.feature import Feature
class DB:

    QUERY_FEATURES_INFO_SQL = """
    SELECT feature_id, text
    FROM newbies_feature
    WHERE feature_id IN (%s)
    ORDER BY feature_id DESC;
    """

    QUERY_COMMITS_INFO_SQL = """
    SELECT * FROM commit_info WHERE commit_id IN (%s)
    ORDER BY FIELD(commit_id, %s);
    """

    QUERY_COMMITS_BY_FEATURE_SQL = """
    SELECT commit_id FROM newbies_mapping
        WHERE feature_id = %s
        ORDER BY id ASC;
    """

    QUERY_FEATURES_ALL_SQL = """
    SELECT feature_id, h1, h2, text, version
        FROM newbies_feature
        WHERE 1=1
        ORDER BY feature_id DESC;
    """

    QUERY_FEATURES_ALL_NEW_SQL = """
    SELECT feature_id, h1, h2, text, version
        FROM newbies_feature_n
        WHERE 1=1
        ORDER BY feature_id DESC;
    """

    QUERY_FEATURES_VERSION_SQL = """
    SELECT feature_id, text, version
        FROM newbies_feature
        WHERE version = %s
        ORDER BY feature_id DESC;
    """

    QUERY_FEATURES_MM_SQL = """
    SELECT feature_id, text, version
        FROM newbies_feature
        WHERE h1 = 'Memory management' and version = '6.6'
        ORDER BY feature_id DESC;
    """ 

    QUERY_FEATURES_MM_H_SQL = """
    SELECT feature_id, h1, h2, text, version
        FROM newbies_feature
        WHERE h1 = 'Memory management'
        ORDER BY feature_id DESC;
    """ 

    INSERT_COMMIT_INFO_SQL = """
    INSERT INTO commit_info (commit_id, commit_subject, commit_message)
        VALUES (%s, %s, %s);
    """

    INSERT_ENTITY_SQL = """
    INSERT INTO entities_ext (
        name_en, name_cn, source, definition_en, definition_cn,
        aliases, rel_desc, wikidata_id, feature_id, type, class
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    );
    """

    # 添加有效的type枚举值
    VALID_ENTITY_TYPES = {'link', 'fusion'}  # 定义允许的type值集合

    def __init__(self, config):
        try:
            self.connection = pymysql.connect(**config.DB_CONFIG)
            print("Database connection established successfully.")
        except pymysql.MySQLError as e:
            print(f"Error connecting to database: {e}")
            raise
    
    def __del__(self):
        self.connection.close()

    def get_features_info(self, feature_ids: list[int]):
        """获取一组特性的信息，包括文本，顺序与输入的 feature_ids 一致"""
        cursor = self.connection.cursor()
        # 将 feature_ids 转换为逗号分隔的字符串
        formatted_ids = ','.join(['%s'] * len(feature_ids))
        cursor.execute(self.QUERY_FEATURES_INFO_SQL % formatted_ids, feature_ids)
        result = cursor.fetchall()
        return [text for _, text in result]

    def get_commits_info(self, commit_ids: list[str]):
        """获取一组提交的信息，包括提交主题和消息，顺序与输入的 commit_ids 一致，返回值为字符串列表"""
        if not commit_ids:
            return []  # 如果 commit_ids 为空，直接返回空列表

        cursor = self.connection.cursor()
        # 将 commit_ids 转换为逗号分隔的字符串
        formatted_ids = ','.join(['%s'] * len(commit_ids))
        query = self.QUERY_COMMITS_INFO_SQL % (formatted_ids, formatted_ids)
        cursor.execute(query, commit_ids * 2)
        result = cursor.fetchall()
        return [self._join_commit_info(commit_subject, commit_message)
                for _, commit_subject, commit_message in result]

    def get_commits_by_feature(self, feature_id: int):
        """获取某个特性相关的所有提交的id"""
        cursor = self.connection.cursor()
        cursor.execute(self.QUERY_COMMITS_BY_FEATURE_SQL, (feature_id,))
        result = cursor.fetchall()
        return [commit_id for commit_id, in result]

    def get_all_features(self):
        """获取所有特性的信息，返回Feature对象列表"""
        cursor = self.connection.cursor()
        cursor.execute(self.QUERY_FEATURES_ALL_SQL)
        result = cursor.fetchall()
        # 将查询结果转换为Feature对象列表
        features = []
        for feature_id, h1, h2, text, version in result:
            feature = Feature(
                feature_id=feature_id,
                h1=h1,
                h2=h2,
                feature_description=text,
                version=version
            )
            features.append(feature)
        return features
    
    def get_all_features_new(self):
        """获取所有特性的信息，返回Feature对象列表"""
        cursor = self.connection.cursor()
        # cursor.execute(self.QUERY_FEATURES_ALL_NEW_SQL)
        cursor.execute(self.QUERY_FEATURES_MM_H_SQL)
        result = cursor.fetchall()
        # 将查询结果转换为Feature对象列表
        features = []
        for feature_id, h1, h2, text, version in result:
            feature = Feature(
                feature_id=feature_id,
                h1=h1,
                h2=h2,
                feature_description=text,
                version=version
            )
            features.append(feature)
        return features

    def insert_commit_info(self, commit_id: str, commit_subject: str, commit_message: str):
        """插入一条提交的信息"""
        cursor = self.connection.cursor()
        cursor.execute(self.INSERT_COMMIT_INFO_SQL, (commit_id, commit_subject, commit_message))
        self.connection.commit()

    def _join_commit_info(self, commit_subject: str, commit_message: str) -> str:
        return f"commit_subject:\n{commit_subject}\ncommit_message:\n{commit_message}\n"
    
    def close(self):
        self.connection.close()

    def insert_entity(self, entity_data: dict):
        """插入一条实体数据到entities表
        
        Args:
            entity_data: 包含实体信息的字典，包括name_en, name_cn等字段
        
        Returns:
            bool: 插入是否成功
            
        Raises:
            pymysql.Error: 当数据库操作出错时
        """
        try:
            # 检查连接是否有效
            if not self.connection.open:
                print("Database connection is not open. Reconnecting...")
                self.connection.ping(reconnect=True)
            
            # 验证type字段
            entity_type = entity_data.get('type', '')
            if not entity_type:
                raise ValueError("Entity type cannot be empty")
            if entity_type not in self.VALID_ENTITY_TYPES:
                raise ValueError(f"Invalid entity type: {entity_type}. Must be one of: {', '.join(self.VALID_ENTITY_TYPES)}")
            
            # 使用改进后的entity_exists函数检查实体是否存在
            exists = self.entity_exists(
                entity_name=entity_data['name_en'],
                entity_type=entity_type,
                source=entity_data.get('source', '')
            )
            
            if exists:
                # 如果实体已存在，获取现有的feature_id并更新
                cursor = self.connection.cursor()
                cursor.execute("SELECT feature_id FROM entities_ext WHERE name_en = %s", (entity_data['name_en'],))
                existing_record = cursor.fetchone()
                
                existing_feature_ids = json.loads(existing_record[0]) if existing_record[0] else []
                new_feature_id = entity_data.get('feature_id', [])[0]  # 假设新数据中只有一个feature_id
                
                # 检查新的feature_id是否已存在
                if new_feature_id not in existing_feature_ids:
                    # 将新的feature_id添加到列表中
                    existing_feature_ids.append(new_feature_id)
                    # 更新数据库中的feature_id字段
                    cursor.execute("UPDATE entities_ext SET feature_id = %s WHERE name_en = %s",
                                 (json.dumps(existing_feature_ids), entity_data['name_en']))
                    self.connection.commit()
                    print(f"Updated feature_id for entity {entity_data['name_en']}")
                return

            # 如果实体不存在，执行插入操作
            required_fields = ['name_en', 'type']
            for field in required_fields:
                if not entity_data.get(field):
                    raise ValueError(f"Required field '{field}' is empty or missing")
            
            values = (
                entity_data.get('name_en', ''),
                entity_data.get('name_cn', ''),
                entity_data.get('source', ''),
                entity_data.get('definition_en', ''),
                entity_data.get('definition_cn', ''),
                json.dumps(entity_data.get('aliases', [])),
                entity_data.get('rel_desc', ''),
                entity_data.get('wikidata_id', ''),
                json.dumps(entity_data.get('feature_id', [])),
                entity_type,
                entity_data.get('class', '')
            )
            
            cursor = self.connection.cursor()
            cursor.execute(self.INSERT_ENTITY_SQL, values)
            self.connection.commit()
            print(f"Inserted new entity: {entity_data['name_en']}")

        except Exception as e:
            self.connection.rollback()
            raise ValueError(f"Failed to insert/update entity: {str(e)}")

    def entity_exists(self, entity_name: str, entity_type: str = None, source: str = None) -> bool:
        """检查实体是否存在于 entities_ext 表中
        
        Args:
            entity_name: 实体名称
            entity_type: 实体类型 ('link' 或 'fusion')
            source: 实体来源 (用于 'link' 类型的实体判断)
        
        Returns:
            bool: 实体是否存在
        """
        try:
            cursor = self.connection.cursor()
            
            query = """
            SELECT COUNT(*) FROM entities_ext 
            WHERE name_en = %s 
            AND (
                (type = 'fusion') 
                OR 
                (type = 'link' AND source = %s)
            )
            """
            cursor.execute(query, (entity_name, source))
            result = cursor.fetchone()
            return result[0] > 0
            
        except Exception as e:
            print(f"Error checking entity existence: {str(e)}")
            return False


# class PipelineConfig:
#     # 数据库配置
#     DB_CONFIG = {
#         'host': '10.176.34.96',
#         'port': 3306,
#         'user': 'root',
#         'password': '3edc@WSX!QAZ',
#         'database': 'linuxDatabase',
#         'charset': 'utf8mb4'
#     }

# """测试"""
# if __name__ == "__main__":
#     config = PipelineConfig()
#     db = DB(config)
#     print(db.get_all_features())
