import pymysql
from bs4 import BeautifulSoup
import requests
from prompts.expand import expandPrompt
from prompts.extract import extractPrompt
from utils.deepseek import deepseek
import json
import logging
from datetime import datetime

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
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # 提取 commit-subject 和 commit-msg 两个 div 的 text
    commit_subject = soup.find('div', class_='commit-subject').text
    commit_msg = soup.find('div', class_='commit-msg').text

    return {"commit_subject": commit_subject, "commit_message": commit_msg}

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

        logger.info(f"Processing feature {id + 1}/{len(mm_features)}")

        # 查询 feature_id 对应的 commit
        cursor.execute(query_commit_sql, (feature_id,))
        commit_ids = cursor.fetchall()
        commits = []
        for _, commit_id in commit_ids:
            commit = curl_commit(commit_id)
            commits.append(commit)
        
        prompt = expandPrompt(feature_description=feature_description, commits=commits).format()
        expand_response = llm.get_response(prompt)
        expand_response = strip_json(expand_response)

        # 反序列化，拼接得到扩写后的 feature 信息
        expand_object = json.loads(expand_response)
        feature_expanded = {
            "feature_description": feature_description,
            "commits": commits,
            **expand_object
        }

        prompt = extractPrompt(**feature_expanded).format()
        extract_response = llm.get_response(prompt)
        extract_response = strip_json(extract_response)

        # 反序列化，拼接得到提取实体后的 feature 信息
        extract_object = json.loads(extract_response)
        feature_extracted = {
            "feature_id": feature_id,
            "feature_description": feature_description,
            "version": version,
            "commits": commits,
            **expand_object,
            **extract_object
        }

        logger.debug(f"feature_extracted of feature_id={feature_id}:\n{json.dumps(feature_extracted, ensure_ascii=False, indent=4)}")

        features_output.append(feature_extracted)

        if id % 10 == 9:
            # 写入文件
            with open(f'data/features/features_output_{nowtime}.json', 'w') as f:
                json.dump(features_output, f, indent=4)

    # 写入文件
    with open(f'data/features/features_output_{nowtime}.json', 'w') as f:
        json.dump(features_output, f, indent=4)

    # 关闭数据库连接
    connection.close()

if __name__ == '__main__':
    main()