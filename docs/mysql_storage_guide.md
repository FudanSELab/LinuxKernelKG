# MySQL Database Storage for Entity Linking

这个指南描述了如何使用新的MySQL数据库存储功能来保存实体链接结果。

## 概述

新的数据库存储功能允许你将实体链接结果直接保存到MySQL数据库中，而不是JSON文件。这提供了以下优势：

- **断点续传**: 自动从上次处理的位置继续
- **数据完整性**: 使用数据库事务保证数据一致性
- **别名支持**: 正确处理实体别名的存储
- **查询能力**: 支持复杂的SQL查询和分析
- **并发安全**: 支持多进程并发写入

## 数据库表结构

### 主实体表 (entities_extraction)

```sql
CREATE TABLE `entities_extraction` (
  `eid` bigint NOT NULL AUTO_INCREMENT COMMENT '唯一id，整型递增',
  `name_en` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '英文名称',
  `name_cn` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '中文名称',
  `source` varchar(1024) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `definition_en` text COLLATE utf8mb4_unicode_ci COMMENT '对概念的定义（英文）',
  `definition_cn` text COLLATE utf8mb4_unicode_ci COMMENT '对概念的定义（中文）',
  `aliases` text COLLATE utf8mb4_unicode_ci COMMENT '别名JSON数组',
  `rel_desc` text COLLATE utf8mb4_unicode_ci COMMENT '相关描述JSON数组',
  `wikidata_id` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'wikidata的id',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `feature_id` int NOT NULL,
  PRIMARY KEY (`eid`),
  UNIQUE KEY `unique_name_feature` (`name_en`,`feature_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 别名表 (entity_aliases)

```sql
CREATE TABLE `entity_aliases` (
  `alias_id` bigint NOT NULL AUTO_INCREMENT COMMENT '别名表的唯一ID',
  `eid` bigint NOT NULL COMMENT '外键，关联到 entities_extraction 表的 eid',
  `name_en` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '别名的英文名称',
  `name_cn` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '别名的中文名称',
  `source` varchar(1024) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '别名的来源',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`alias_id`),
  KEY `idx_eid` (`eid`),
  KEY `idx_name_en` (`name_en`),
  KEY `idx_name_cn` (`name_cn`),
  UNIQUE KEY `unique_alias_for_entity` (`eid`, `name_en`, `name_cn`),
  CONSTRAINT `fk_alias_to_entity` FOREIGN KEY (`eid`) REFERENCES `entities_extraction` (`eid`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

## 配置

数据库连接配置位于 `config/pipeline_config.py`:

```python
DB_CONFIG = {
    'host': '10.176.34.96',
    'port': 3306,
    'user': 'root',
    'password': '3edc@WSX!QAZ',
    'database': 'linuxDatabase',
    'charset': 'utf8mb4'
}
```

## 使用方法

### 基本使用

```bash
# 运行实体链接并保存到数据库
python scripts/run_entity_link_db.py

# 使用自定义输入文件
python scripts/run_entity_link_db.py --input my_entities.jsonl

# 调整批处理大小
python scripts/run_entity_link_db.py --batch-size 20
```

### 高级选项

```bash
# 限制处理的最大feature_id
python scripts/run_entity_link_db.py --max-feature-id 50000

# 从头开始（不使用断点续传）
python scripts/run_entity_link_db.py --no-resume

# 测试数据库连接
python scripts/run_entity_link_db.py --test-db
```

### 断点续传

脚本会自动检测数据库中最后处理的feature_id，并从下一个开始继续处理：

```bash
# 第一次运行
python scripts/run_entity_link_db.py --max-feature-id 1000

# 中断后继续运行（自动从feature_id 1001开始）
python scripts/run_entity_link_db.py --max-feature-id 2000
```

## 测试和演示

### 运行完整演示

```bash
# 运行数据库功能演示
python examples/entity_linking_database_demo.py

# 查看演示结果
# 然后清理演示数据
python scripts/cleanup_demo_data.py
```

### 测试数据库连接

```bash
# 简单连接测试
python scripts/test_db_connection.py

# 脚本内置测试
python scripts/run_entity_link_db.py --test-db
```

## 监控和维护

### 检查处理进度

```sql
-- 查看最后处理的feature_id
SELECT MAX(feature_id) as last_processed FROM entities_extraction;

-- 统计各feature_id的实体数量
SELECT feature_id, COUNT(*) as entity_count 
FROM entities_extraction 
GROUP BY feature_id 
ORDER BY feature_id DESC 
LIMIT 10;

-- 查看最近添加的实体
SELECT eid, name_en, feature_id, create_time 
FROM entities_extraction 
ORDER BY create_time DESC 
LIMIT 10;
```

### 统计信息

```sql
-- 实体总数
SELECT COUNT(*) as total_entities FROM entities_extraction;

-- 别名总数
SELECT COUNT(*) as total_aliases FROM entity_aliases;

-- 有别名的实体数量
SELECT COUNT(DISTINCT eid) as entities_with_aliases FROM entity_aliases;

-- 平均每个实体的别名数量
SELECT AVG(alias_count) as avg_aliases_per_entity
FROM (
    SELECT eid, COUNT(*) as alias_count 
    FROM entity_aliases 
    GROUP BY eid
) t;
```

## 故障排除

### 常见问题

1. **数据库连接失败**
   ```bash
   python scripts/run_entity_link_db.py --test-db
   ```

2. **重复键错误**
   - 检查是否存在重复的 (name_en, feature_id) 组合
   - 脚本会自动跳过已存在的实体

3. **内存使用过高**
   - 减少batch_size参数
   - 使用max_feature_id限制处理范围

4. **处理中断**
   - 重新运行脚本，会自动从断点继续
   - 或使用--no-resume从头开始

### 性能优化

- 使用合适的batch_size（默认10，可调整为20-50）
- 确保数据库索引正确创建
- 监控数据库连接池使用情况
- 定期清理日志文件

## 数据导出

### 导出为JSON格式

```python
# 导出脚本示例
import json
from database.mysql_manager import MySQLManager
from config.pipeline_config import PipelineConfig

db_manager = MySQLManager(PipelineConfig)
with db_manager.get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM entities_extraction")
    entities = cursor.fetchall()
    
    with open('exported_entities.json', 'w', encoding='utf-8') as f:
        json.dump(entities, f, ensure_ascii=False, indent=2, default=str)
```

## 备份建议

- 定期备份数据库
- 保留原始JSONL输入文件
- 记录处理日志以便追溯
- 测试恢复流程

## 扩展功能

数据库存储为未来功能扩展提供了基础：

- 实体关系存储
- 版本控制
- 并发处理
- 分布式处理
- 实时查询API 