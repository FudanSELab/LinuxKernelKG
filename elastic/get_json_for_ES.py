import os
import json
import requests
from requests.auth import HTTPBasicAuth
from elasticsearch import Elasticsearch


def append_bulk_entry(json_filename, id_value, name_value, content_value):
    """
    向文件中追加两行数据：
      第一行：操作元数据，格式为 {"index": {"_id": id_value}}
      第二行：实际数据文档，格式为 {"name": name_value, "content": content_value}
    每一行末尾都会添加一个换行符。

    :param json_filename: 要写入的 JSON 文件路径
    :param id_value: 文档的 _id 值
    :param name_value: 文档中 "name" 字段的值
    :param content_value: 文档中 "content" 字段的值
    """
    metadata = {"index": {"_id": id_value}}
    document = {"name": name_value, "content": content_value}

    with open(json_filename, 'a', encoding='utf-8') as f:
        f.write(json.dumps(metadata) + "\n")
        f.write(json.dumps(document) + "\n")


def process_rst_files(directory, output_json_file):
    """
    遍历指定目录（包括子目录）下所有 .rst 文件，并将每个文件的路径和内容保存到指定的 JSON 文件中，
    格式符合 Elasticsearch bulk API 的要求。

    :param directory: 要遍历的目录路径
    :param output_json_file: 输出的 JSON 文件路径
    """
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(".rst"):
                full_path = os.path.join(root, file)
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except Exception as e:
                    print(f"无法读取文件 {full_path}: {e}")
                    continue

                # 这里使用文件的完整路径作为 _id 和 name 字段的值
                pos = full_path.find("Documentation")
                full_path = full_path[pos:]
                append_bulk_entry(output_json_file, full_path, full_path, content)


def upload_json_to_es(json_filepath, index_name, es_host="https://localhost:9200", es_username=None, es_password=None):
    """
    将指定 JSON 文件的内容上传到 Elasticsearch 的 bulk API 接口。

    :param json_filepath: JSON 文件路径（包含 bulk 格式数据）
    :param index_name: Elasticsearch 索引名称
    :param es_host: Elasticsearch 主机地址，默认为 "https://localhost:9200"
    :param es_username: Elasticsearch 用户名
    :param es_password: Elasticsearch 密码
    """
    headers = {"Content-Type": "application/json"}
    url = f"{es_host}/{index_name}/_bulk?pretty&refresh"

    try:
        with open(json_filepath, 'rb') as f:
            data = f.read()
    except Exception as e:
        print(f"读取文件 {json_filepath} 时出错：{e}")
        return

    # 如果提供了用户名和密码，则使用 HTTP 基本认证
    if es_username and es_password:
        auth = HTTPBasicAuth(es_username, es_password)
    else:
        auth = None

    response = requests.post(url, headers=headers, data=data, auth=auth, verify=False)

    if response.ok:
        print("上传成功！返回结果：")
    else:
        print("上传失败！状态码：", response.status_code)

    print(response.text)


def delete_index(index_name, es_host="https://localhost:9200", es_username="elastic",
                 es_password="TswX*cZOniCzm8S8aWbG"):
    """
    删除指定的 Elasticsearch 索引。

    :param index_name: 要删除的索引名称
    :param es_host: Elasticsearch 主机地址，默认为 "https://localhost:9200"
    """
    # 创建 Elasticsearch 客户端
    es = Elasticsearch(
        es_host,
        basic_auth=(es_username, es_password),
        verify_certs=False
    )

    # 检查索引是否存在
    if es.indices.exists(index=index_name):
        # 删除索引
        es.indices.delete(index=index_name)
        print(f"索引 '{index_name}' 已成功删除。")
    else:
        print(f"索引 '{index_name}' 不存在。")


def search_all_content_by_keyword(keyword, index_name="fjy_index", es_host="https://localhost:9200",
                                  es_username=None, es_password=None, batch_size=1000):
    """
    使用 `search_after` 查询包含指定关键词的所有文档，并将结果存入 JSON 文件。

    :param keyword: 要搜索的关键词
    :param index_name: Elasticsearch 索引名称，默认为 "fjy_index"
    :param es_host: Elasticsearch 主机地址，默认为 "https://localhost:9200"
    :param es_username: Elasticsearch 用户名
    :param es_password: Elasticsearch 密码
    :param batch_size: 每次请求返回的文档数
    """
    # 创建 Elasticsearch 客户端
    es = Elasticsearch(
        es_host,
        basic_auth=(es_username, es_password) if es_username and es_password else None,
        verify_certs=False
    )

    results = []  # 存储所有查询结果
    search_after_value = None  # 用于 `search_after` 机制
    query = {
        "size": batch_size,
        "sort": ["_doc"],  # 使用 _doc 作为排序字段
        "query": {
            "match": {"content": keyword}
        }
    }

    while True:
        if search_after_value:
            query["search_after"] = search_after_value  # 设置游标

        response = es.search(index=index_name, body=query)
        hits = response.get("hits", {}).get("hits", [])

        if not hits:
            break  # 如果没有更多结果，退出循环

        results.extend([hit["_source"] for hit in hits])
        search_after_value = hits[-1]["sort"]  # 取最后一条数据的 `sort` 值

    # 将查询结果存入 JSON 文件
    length = len(results)
    with open(f"output/lkdoc_[{keyword}]_{length}.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
    print(f"{length}条查询结果已保存")


# 示例调用：
if __name__ == "__main__":
    rst_directory = "linux-6.13.2/linux-6.13.2/Documentation"  # root/documentation
    index_file = "data/lkdoc.json"  # 输出文件路径
    es_username = "elastic"  # ES 用户名
    es_password = "TswX*cZOniCzm8S8aWbG"  # ES 密码

    # 生成JSON 文件
    # process_rst_files(rst_directory, output_file)
    # print("json文件已生成！")

    # 上传索引
    upload_json_to_es(index_file, index_name="fjy_index", es_username=es_username, es_password=es_password)

    # 删除索引
    # index_to_delete = "fjy_index"  # 替换为您要删除的索引名称
    # delete_index(index_to_delete, es_username=es_username, es_password=es_password)

    # 在索引中搜索关键词
    keyword = "damon"
    search_all_content_by_keyword(keyword, index_name="fjy_index", es_username=es_username, es_password=es_password)
