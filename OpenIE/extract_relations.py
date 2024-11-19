import mysql.connector
import requests

# 数据库配置
DB_CONFIG = {
    'host': '127.0.0.1',  # 替换为你的 MySQL 主机
    'user': 'root',  # 替换为你的用户名
    'password': '',  # 替换为你的密码
    'database': 'Digital_Twin_of_Linux',  # 替换为你的数据库名
    'charset': 'utf8mb4'
}

# CoreNLP Server 配置
CORENLP_URL = "http://localhost:9000"


# 创建 relation 表（如果不存在）
def create_relation_table():
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS relation (
        relation_id INT AUTO_INCREMENT PRIMARY KEY,
        subject TEXT NOT NULL,
        relation TEXT NOT NULL,
        object TEXT NOT NULL,
        sentence_id INT NOT NULL,
        FOREIGN KEY (sentence_id) REFERENCES sentences(sentence_id)
    )
    """
    cursor.execute(create_table_sql)
    connection.commit()
    cursor.close()
    connection.close()


# 从 MySQL 查询 sentences 表
def fetch_sentences():
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT sentence_id, text FROM sentences")
    sentences = cursor.fetchall()
    cursor.close()
    connection.close()
    return sentences


# 调用 OpenIE 解析
def parse_with_openie(text):
    params = {
        "annotators": "openie",
        "outputFormat": "json",
    }
    response = requests.post(CORENLP_URL, params=params, data=text.encode('utf-8'))
    if response.status_code == 200:
        result = response.json()
        triples = []
        for sentence in result.get("sentences", []):
            for triple in sentence.get("openie", []):
                triples.append((triple["subject"], triple["relation"], triple["object"]))
        return triples
    else:
        print(f"Error in OpenIE call: {response.status_code}, {response.text}")
        return []


# 将解析结果插入 relation 表
def insert_relations(sentence_id, relations):
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()
    for subject, relation, obj in relations:
        cursor.execute(
            "INSERT INTO relation (subject, relation, object, sentence_id) VALUES (%s, %s, %s, %s)",
            (subject, relation, obj, sentence_id)
        )
    connection.commit()
    cursor.close()
    connection.close()


# 主流程
def main():
    # 创建 relation 表
    create_relation_table()

    # 从 sentences 表中查询所有句子
    sentences = fetch_sentences()
    for sentence in sentences:
        sentence_id = sentence["sentence_id"]
        text = sentence["text"]
        print(f"Processing sentence ID {sentence_id}: {text}")

        # 调用 OpenIE 解析句子
        relations = parse_with_openie(text)

        if relations:
            print(f"Extracted {len(relations)} relations.")
            insert_relations(sentence_id, relations)
        else:
            print("No relations extracted.")


if __name__ == "__main__":
    main()
