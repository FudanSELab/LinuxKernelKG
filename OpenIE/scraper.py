import requests
from bs4 import BeautifulSoup
import nltk
import pymysql

# 下载nltk的punkt数据包，用于句子分割
nltk.download('punkt')
nltk.download('punkt_tab')

# MySQL 数据库配置
db_config = {
    'host': '127.0.0.1',  # 替换为你的 MySQL 主机
    'user': 'root',  # 替换为你的用户名
    'password': 'your_password',  # 替换为你的密码
    'database': 'Digital_Twin_of_Linux',  # 替换为你的数据库名
    'charset': 'utf8mb4'
}

# 创建表的 SQL
create_table_sql = """
CREATE TABLE IF NOT EXISTS sentences (
    sentence_id INT AUTO_INCREMENT PRIMARY KEY,
    text TEXT NOT NULL,
    h1 TEXT NOT NULL,
    h2 TEXT,
    h3 TEXT,
    h4 TEXT,
    h5 TEXT,
    source VARCHAR(255) DEFAULT 'wikipedia'
);
"""


# 初始化数据库连接和创建表
def init_db():
    connection = pymysql.connect(**db_config)
    with connection.cursor() as cursor:
        cursor.execute(create_table_sql)
    connection.commit()
    connection.close()


# 插入数据到 MySQL 的函数
def insert_sentence(connection, text, h1, h2, h3, h4, h5, source='wikipedia'):
    insert_sql = """
    INSERT INTO sentences (text, h1, h2, h3, h4, h5, source)
    VALUES (%s, %s, %s, %s, %s, %s, %s);
    """
    with connection.cursor() as cursor:
        cursor.execute(insert_sql, (text, h1, h2, h3, h4, h5, source))
    connection.commit()


# 爬取和提取数据
def extract_titles_and_paragraphs(h1, soup, connection):
    # 删除所有<sup>标签
    for sup in soup.find_all('sup'):
        sup.decompose()

    # 维护标题栈
    title_stack = []

    # 遍历所有标签
    for tag in soup.find_all(['h2', 'h3', 'h4', 'h5', 'p']):
        # 如果是标题标签
        if tag.name in ['h2', 'h3', 'h4', 'h5']:
            # 获取当前标题的级别（数字表示级别，h2 -> 2, h3 -> 3, ...）
            level = int(tag.name[1])

            # 处理标题栈
            while title_stack and title_stack[-1][0] >= level:
                title_stack.pop()  # 弹出比当前标题级别大或相等的标题

            # 将当前标题加入栈
            title_stack.append((level, tag.get_text(strip=True)))

        # 如果是段落标签
        elif tag.name == 'p':
            # 获取当前段落的文本
            paragraph_text = tag.get_text(separator=' ', strip=True)

            # 使用nltk分割段落文本成句子列表
            sentences = nltk.sent_tokenize(paragraph_text)

            # 获取当前栈中的标题，栈中标题最多有4个
            h2 = h3 = h4 = h5 = ""
            if len(title_stack) > 0 and title_stack[0][0] == 2:
                h2 = title_stack[0][1]
            if len(title_stack) > 1 and title_stack[1][0] == 3:
                h3 = title_stack[1][1]
            if len(title_stack) > 2 and title_stack[2][0] == 4:
                h4 = title_stack[2][1]
            if len(title_stack) > 3 and title_stack[3][0] == 5:
                h5 = title_stack[3][1]

            # 保存每个句子到数据库
            for sentence in sentences:
                insert_sentence(connection, sentence, h1, h2, h3, h4, h5)
                print(f"{sentence}, {h1}, {h2}, {h3}, {h4}, {h5}")


# 主程序
if __name__ == '__main__':
    # 初始化数据库
    init_db()

    h1_list = ["Memory_management_(operating_systems)", "Memory_management", "Computer_data_storage", "Virtual_memory",
               "Algorithm", "Memory_mapping", "Scheduling_(computing)", "Data_structure", "Virtual_address_space",
               "Computer_multitasking", "Concurrent_computing", "Memory_paging", "Task_(computing)",
               "Process (computing)", "Thread_(computing)", "Address_space", "Page_(computer_memory)",
               "Memory_management_unit", "Demand_paging", "Memory_segmentation", "Memory_map"]
    for h1 in h1_list:
        print(f"-------------{h1}---------------")
        try:
            # 获取网页内容
            url = f'https://en.wikipedia.org/wiki/{h1}'  # 替换为目标URL
            response = requests.get(url)
            soup = BeautifulSoup(response.content, 'html.parser')

            # 数据库连接
            connection = pymysql.connect(**db_config)

            # 提取并保存数据
            try:
                extract_titles_and_paragraphs(h1, soup, connection)
            finally:
                connection.close()

        except Exception as e:
            print(e)
            print(f"无法打开{h1}对应网页")
