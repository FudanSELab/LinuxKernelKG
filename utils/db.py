import pymysql

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
        WHERE h1 = 'Memory management' and version = '6.6'
        ORDER BY feature_id DESC;
    """

    INSERT_COMMIT_INFO_SQL = """
    INSERT INTO commit_info (commit_id, commit_subject, commit_message)
        VALUES (%s, %s, %s);
    """

    def __init__(self, config):
        self.connection = pymysql.connect(**config.DB_CONFIG)
    
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
