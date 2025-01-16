import pymysql
import json

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
    SELECT feature_id, text, version
        FROM newbies_feature
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

    INSERT_COMMIT_INFO_SQL = """
    INSERT INTO commit_info (commit_id, commit_subject, commit_message)
        VALUES (%s, %s, %s);
    """

    INSERT_ENTITY_SQL = """
    INSERT INTO entities_extraction (
        name_en, name_cn, source, definition_en, definition_cn,
        aliases, rel_desc, wikidata_id, feature_id, create_time, update_time
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
    );
    """

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
        """获取所有特性的信息，暂时只有 mm 和 6.6 版本"""
        cursor = self.connection.cursor()
        cursor.execute(self.QUERY_FEATURES_ALL_SQL)
        result = cursor.fetchall()
        return [{"feature_id": feature_id, "feature_description": text, "version": version} for feature_id, text, version in result]

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
            
            with self.connection.cursor() as cursor:
                # 验证必要字段
                required_fields = ['name_en']
                for field in required_fields:
                    if not entity_data.get(field):
                        print(f"Error: Required field '{field}' is empty or missing")
                        return False
                
                values = (
                    entity_data.get('name_en', ''),
                    entity_data.get('name_cn', ''),
                    entity_data.get('source', ''),
                    entity_data.get('definition_en', ''),
                    entity_data.get('definition_cn', ''),
                    json.dumps(entity_data.get('aliases', [])),
                    entity_data.get('rel_desc', ''),
                    entity_data.get('wikidata_id', ''),
                    entity_data.get('feature_id', '')
                )
            
                
                cursor.execute(self.INSERT_ENTITY_SQL, values)
                self.connection.commit()
                print(f"Successfully inserted entity: {entity_data.get('name_en')}")
                return True
            
        except pymysql.Error as e:
            print(f"Database error occurred: {repr(e)}")
            self.connection.rollback()
            return False
        except Exception as e:
            print(f"An unexpected error occurred: {repr(e)}")
            return False

    def entity_exists(self, entity_name: str) -> bool:
        """检查实体是否存在于 entities_extraction 表中"""
        query = "SELECT COUNT(*) FROM entities_extraction WHERE name_en = %s"
        cursor = self.connection.cursor()
        cursor.execute(query, (entity_name,))
        result = cursor.fetchone()
        return result[0] > 0


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
