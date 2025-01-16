from utils.logger import setup_logger
from utils.db import DB

class DataCollector:
    def __init__(self, config):
        self.logger = setup_logger('collector')
        self.config = config
        self.db = DB(config)
        
    def collect_features(self, limit=None):
        """从数据库收集特性数据
        
        Args:
            limit (int, optional): 限制返回的特性数量，用于测试。默认为None表示返回所有特性。
        """
        try:
            features = self.db.get_all_features()
            
            if limit:
                features = features[:limit]
                    
            self.logger.info(f"Collected {len(features)} features" + (f" (limited to {limit})" if limit else ""))
            return features
            
        finally:
            self.db.close()
            
    def store_entity(self, entity_data):
        """存储实体数据到数据库
        
        Args:
            entity_data (dict): 实体数据
        """
        try:
            self.db.insert_entity(entity_data)
        except Exception as e:
            self.logger.error(f"Failed to store entity: {repr(e)}")
            raise