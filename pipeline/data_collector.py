import pymysql
from utils.logger import setup_logger

class DataCollector:
    def __init__(self, config):
        self.logger = setup_logger('collector')
        self.config = config
        
    def collect_features(self, limit=None):
        """从数据库收集特性数据
        
        Args:
            limit (int, optional): 限制返回的特性数量，用于测试。默认为None表示返回所有特性。
        """
        connection = pymysql.connect(**self.config.DB_CONFIG)
        try:
            cursor = connection.cursor()
            cursor.execute(self.config.QUERY_MM_SQL)
            features = []
            
            for feature_id, text, version in cursor.fetchall():
                features.append({
                    'feature_id': feature_id,
                    'feature_description': text,
                    'version': version
                })
                if limit and len(features) >= limit:
                    break
                    
            self.logger.info(f"Collected {len(features)} features" + (f" (limited to {limit})" if limit else ""))
            return features
            
        finally:
            connection.close()