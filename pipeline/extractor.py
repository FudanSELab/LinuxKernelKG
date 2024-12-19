import pymysql
from bs4 import BeautifulSoup
import requests
from prompts.extractEntity import extractEntityPrompt
from prompts.extractTriple import extractTriplePrompt
from prompts.extractTripleOpen import extractTripleOpenPrompt
from prompts.verify import verifyPrompt
from utils.deepseek import deepseek
from utils.utils import *
import json
import logging
from datetime import datetime
import time
from tqdm import tqdm
import os
from utils.logger import setup_logger

# MySQL 数据库配置
db_config = {
    'host': '10.176.34.96',  # 实验室主机
    'port': 3306,
    'user': 'root',
    'password': '3edc@WSX!QAZ',
    'database': 'linuxDatabase',
    'charset': 'utf8mb4'
}

# 查询 mm 相关 feature 的 SQL
query_mm_sql = """
SELECT feature_id, text, version
    FROM newbies_feature
	WHERE h1 = 'Memory management' and version = '6.6'
    ORDER BY feature_id DESC;
"""

# 查询 feature_id 对应的 commit 的 SQL
query_commit_sql = """
SELECT id, commit_id FROM newbies_mapping
	WHERE feature_id = %s
    ORDER BY id ASC;
"""

# 初始化 llm
llm = deepseek()


# 日志配置
nowtime = datetime.now().strftime('%Y-%m-%d %H-%M-%S')
log_dir = 'data/log'
os.makedirs(log_dir, exist_ok=True)  # Create the directory if it doesn't exist

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
file_handler = logging.FileHandler(f'{log_dir}/extractor_{nowtime}.log', mode='w', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger = logging.getLogger("extractor")
logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.setLevel(logging.DEBUG)

def clean_commit_message(message):
    # 按行分割消息
    lines = message.split('\n')
    # 定义需要过滤的前缀
    prefixes_to_remove = ['Cc:', 'Link:', 'Signed-off-by:', 'Tested-by:', 'Acked-by:', 'Reported-by:', 'Suggested-by', 'Co-developed-by', 'Reviewed-by']
    # 过滤掉指定前缀开头的行
    filtered_lines = [line for line in lines if not any(line.strip().startswith(prefix) for prefix in prefixes_to_remove)]
    # 重新组合消息
    return '\n'.join(filtered_lines)

# 访问 linux 内核 git 仓库获取 commit subject/message
def curl_commit(commit_id):

    url = f'https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id={commit_id}'

    # get 这一步可能会失败，需要处理异常
    while True:
        try:
            time.sleep(1)
            logger.debug(f"curling url: {url}")
            response = requests.get(url)
            break
        except Exception as e:
            logger.error(f"Request failed in curl_commit(), retrying in 10 seconds: {e}")
            time.sleep(10)

    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # 提取 commit-subject 和 commit-msg 两个 div 的 text
    try:
        commit_subject = soup.find('div', class_='commit-subject').text
        commit_msg = soup.find('div', class_='commit-msg').text
    except Exception as e:
        logger.error(f"failed to extract commit subject and message! commit_id={commit_id}")
        commit_subject = ""
        commit_msg = ""

    # 清洗 commit message
    commit_msg = clean_commit_message(commit_msg)

    return {"commit_subject": commit_subject, "commit_message": commit_msg}


# 查询数据库（如果存在）或者爬网页来获取某个 commit 的 subject 和 message
def get_commit(commit_id, connection):
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM commit_info WHERE commit_id = %s", (commit_id,))
    commit = cursor.fetchone()
    if commit is None:
        commit = curl_commit(commit_id)
        cursor.execute("INSERT INTO commit_info (commit_id, commit_subject, commit_message) VALUES (%s, %s, %s);", (commit_id, commit['commit_subject'], commit['commit_message']))
        connection.commit()
    else:
        commit = {"commit_subject": commit[1], "commit_message": commit[2]}
    return commit


class EntityRelationExtractor:
    def __init__(self, config):
        self.logger = setup_logger()
        self.llm = deepseek()
        self.config = config
        
    def extract_entities_and_relations(self, features):
        """抽取实体和关系"""
        connection = pymysql.connect(**self.config.DB_CONFIG)
        try:
            features_output = []
            for feature in features:
                feature_id = feature['feature_id']
                feature_description = feature['feature_description']
                version = feature['version']
                
                # 获取commits
                cursor = connection.cursor()
                cursor.execute(self.config.QUERY_COMMIT_SQL, (feature_id,))
                commit_ids = cursor.fetchall()
                commits = []
                for _, commit_id in commit_ids:
                    commit = self._get_commit_info(commit_id)
                    commits.append(commit)
                
                # 添加日志记录commits数量
                self.logger.info(f"Processing feature_id {feature_id} with {len(commits)} commits")
                
                entities = []
                triples = []
                
                # 简单的分组处理，无论commits数量多少
                for i in range(0, len(commits), 5):
                    commits_group = commits[i:i+5]
                    
                    # 实体抽取
                    prompt_entity = extractEntityPrompt(
                        feature_description=feature_description, 
                        commits=commits_group
                    ).format()
                    response_entity = self.llm.get_response(prompt_entity)
                    object_entity = json.loads(strip_json(response_entity))
                    
                    # 关系抽取
                    prompt_triple = extractTriplePrompt(
                        feature_description=feature_description, 
                        commits=commits_group
                    ).format()
                    response_triple = self.llm.get_response(prompt_triple)
                    object_triple = json.loads(strip_json(response_triple))
                    
                    # 开放关系抽取
                    prompt_tripleOpen = extractTripleOpenPrompt(
                        feature_description=feature_description, 
                        commits=commits_group
                    ).format()
                    response_tripleOpen = self.llm.get_response(prompt_tripleOpen)
                    object_tripleOpen = json.loads(strip_json(response_tripleOpen))
                    
                    # 合并三元组
                    all_triples = object_triple['triples'] + object_tripleOpen['triples']
                    
                    # 验证
                    prompt_verify = verifyPrompt(
                        feature_description=feature_description,
                        commits=commits_group,
                        entities=object_entity['entities'],
                        triples=all_triples
                    ).format()
                    response_verify = self.llm.get_response(prompt_verify)
                    object_verify = json.loads(strip_json(response_verify))
                    
                    # 去重添加
                    entities.extend([e for e in object_verify['entities'] if e not in entities])
                    triples.extend([t for t in object_verify['triples'] if t not in triples])
                
                feature_extracted = {
                    "feature_id": feature_id,
                    "feature_description": feature_description,
                    "version": version,
                    "commits": commits,
                    "entities": entities,
                    "triples": triples
                }
                features_output.append(feature_extracted)
                
            return features_output
            
        finally:
            connection.close()
            
    def _get_commit_info(self, commit_id):
        """获取commit信息"""
        url = f'https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id={commit_id}'
        
        # 重试机制
        for _ in range(self.config.MAX_RETRIES):
            try:
                response = requests.get(url)
                soup = BeautifulSoup(response.text, 'html.parser')
                commit_subject = soup.find('div', class_='commit-subject').text
                commit_msg = soup.find('div', class_='commit-msg').text
                commit_msg = clean_commit_message(commit_msg)
                return {
                    "commit_subject": commit_subject,
                    "commit_message": commit_msg
                }
            except Exception as e:
                self.logger.error(f"Request failed: {e}, retrying...")
                time.sleep(1)
        
        self.logger.error(f"Failed to get commit info for {commit_id}")
        return {
            "commit_subject": "",
            "commit_message": ""
        }