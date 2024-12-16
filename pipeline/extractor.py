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
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
file_handler = logging.FileHandler(f'data/log/extractor_{nowtime}.log', mode='w', encoding='utf-8')
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


def main():

    # 建立数据库连接
    connection = pymysql.connect(**db_config)
    cursor = connection.cursor()

    # 查询 mm 相关 feature
    cursor.execute(query_mm_sql)
    mm_features = cursor.fetchall()

    # 输出
    features_output = []

    for id, (feature_id, feature_description, version) in enumerate(mm_features):
        
        if id < 13:
            continue

        logger.info(f"---------Processing feature {id + 1}/{len(mm_features)}---------")

        # 查询 feature_id 对应的 commit
        cursor.execute(query_commit_sql, (feature_id,))
        commit_ids = cursor.fetchall()
        commits = []
        for _, commit_id in tqdm(commit_ids, desc=f"curling commits of feature {id + 1}", leave=False):
            commit = get_commit(commit_id, connection)
            commits.append(commit)

        entities = []
        triples = []

        # 至多 5 个 commit 为一组
        for group_index, i in enumerate(range(0, len(commits), 5)):
            commits_group = commits[i:i+5]
            prompt_entity = extractEntityPrompt(feature_description=feature_description, commits=commits_group).format()
            response_entity = llm.get_response(prompt_entity)
            response_entity = strip_json(response_entity)
            object_entity = json.loads(response_entity)

            prompt_triple = extractTriplePrompt(feature_description=feature_description, commits=commits_group).format()
            response_triple = llm.get_response(prompt_triple)
            response_triple = strip_json(response_triple)
            object_triple = json.loads(response_triple)

            prompt_tripleOpen = extractTripleOpenPrompt(feature_description=feature_description, commits=commits_group).format()
            response_tripleOpen = llm.get_response(prompt_tripleOpen)
            response_tripleOpen = strip_json(response_tripleOpen)
            object_tripleOpen = json.loads(response_tripleOpen)

            # 合并两种方式得到的三元组
            all_triples = object_triple['triples'] + object_tripleOpen['triples']

            # 验证实体和关系三元组
            prompt_verify = verifyPrompt(feature_description=feature_description, commits=commits_group, entities=object_entity['entities'], triples=all_triples).format()
            response_verify = llm.get_response(prompt_verify)
            response_verify = strip_json(response_verify)
            object_verify = json.loads(response_verify)

            # 去重添加实体和关系
            entities.extend([e for e in object_verify['entities'] if e not in entities])
            triples.extend([t for t in object_verify['triples'] if t not in triples])

            logger.debug(f"feature_id={feature_id}, group={group_index}, object_entity: {object_entity}")
            logger.debug(f"feature_id={feature_id}, group={group_index}, object_triple: {object_triple}")
            logger.debug(f"feature_id={feature_id}, group={group_index}, object_tripleOpen: {object_tripleOpen}")
            logger.debug(f"feature_id={feature_id}, group={group_index}, object_verify: {object_verify}")



        feature_extracted = {
            "feature_id": feature_id,
            "feature_description": feature_description,
            "version": version,
            "commits": commits,
            "entities": entities,
            "triples": triples
        }

        logger.debug(f"feature_extracted of feature_id={feature_id}:\n{json.dumps(feature_extracted, ensure_ascii=False, indent=4)}")

        features_output.append(feature_extracted)

        # 写入文件
        with open(f'data/features/features_output_{nowtime}.json', 'w') as f:
            json.dump(features_output, f, indent=4, ensure_ascii=False)

    # 关闭数据库连接
    connection.close()

if __name__ == '__main__':
    main()