import pymysql
from bs4 import BeautifulSoup
import requests
from prompts.extractEntity import extractEntityPrompt
from prompts.extractTriple import extractTriplePrompt
from utils.deepseek import deepseek
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
	WHERE h1 = 'Memory management'
    ORDER BY feature_id DESC;
"""

# 查询 feature_id 对应的 commit 的 SQL
query_commit_sql = """
SELECT min(id) as minimum_id, commit_id FROM feature_file
	WHERE feature_id = %s
    GROUP BY commit_id
    ORDER BY minimum_id;
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
    commit_subject = soup.find('div', class_='commit-subject').text
    commit_msg = soup.find('div', class_='commit-msg').text

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


# 去除 llm response 的开头 ```json 和末尾 ``` 两行
def strip_json(json_str):
    return json_str.lstrip('```json').rstrip('```')


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
        
        logger.info(f"---------Processing feature {id + 1}/{len(mm_features)}---------")

        if version != '6.6':
            continue

        # 查询 feature_id 对应的 commit
        cursor.execute(query_commit_sql, (feature_id,))
        commit_ids = cursor.fetchall()
        commits = []
        for _, commit_id in tqdm(commit_ids, desc=f"curling commits of feature {id + 1}", leave=False):
            commit = get_commit(commit_id, connection)
            commits.append(commit)

        prompt_entity = extractEntityPrompt(feature_description=feature_description, commits=commits).format()
        response_entity = llm.get_response(prompt_entity)
        response_entity = strip_json(response_entity)
        object_entity = json.loads(response_entity)

        prompt_triple = extractTriplePrompt(feature_description=feature_description, commits=commits).format()
        response_triple = llm.get_response(prompt_triple)
        response_triple = strip_json(response_triple)
        object_triple = json.loads(response_triple)

        feature_extracted = {
            "feature_id": feature_id,
            "feature_description": feature_description,
            "version": version,
            "commits": commits,
            **object_entity,
            **object_triple
        }

        logger.debug(f"feature_extracted of feature_id={feature_id}:\n{json.dumps(feature_extracted, ensure_ascii=False, indent=4)}")

        features_output.append(feature_extracted)

        break

        # 写入文件
        if id % 10 == 0:
            with open(f'data/features/features_output_{nowtime}.json', 'w') as f:
                json.dump(feature_extracted, f, indent=4, ensure_ascii=False)

    # 写入文件
    with open(f'data/features/features_output_{nowtime}.json', 'w') as f:
        json.dump(feature_extracted, f, indent=4, ensure_ascii=False)

    # 关闭数据库连接
    connection.close()

if __name__ == '__main__':
    main()