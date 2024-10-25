# -*- coding: utf-8 -*-
import logging
from openai import OpenAI
import httpx
import os
import json
import re
import csv
from datetime import datetime

# 解决SSLEOFError
os.environ["http_proxy"] = "http://127.0.0.1:7890"
os.environ["https_proxy"] = "http://127.0.0.1:7890"

client = OpenAI(
    base_url="https://openkey.cloud/v1",
    api_key="sk-xjRtQqLHR1HOgE2F5aDdAf60204f4575841fE0A530Da3d94",
    http_client=httpx.Client(
        base_url="https://api.xty.app/v1",
        follow_redirects=True,
    ),
)


def get_GPT_response(prompt):
    try:
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]

        response = client.chat.completions.create(
            # response = openai.ChatCompletion.create(
            max_tokens=16000,
            temperature=0.2,
            model="gpt-4o-mini",
            messages=messages
        )

        # return response.choices[0]["message"]["content"]
        res = response.choices[0].message.content
        return res
    except Exception as e:
        print(f"发生错误: {e}")


# 检查GPT的返回结果是否严格为Python列表格式
def check_format(children_nodes):
    prompt = (f"假设你是一位格式检查员，请你检查：下面【】中的内容是否是一个严格的Python列表格式（包含空列表）。"
              f"如果是一个严格的Python列表格式（包含空列表），则严格原样返回该列表，不要返回任何其它内容。"
              f"如果除了列表还有其它内容（比如列表外的引号、单词等），则丢弃，严格以一个Python列表的格式返回，不要返回任何其它内容。"
              f"例如：待检查内容为：```python[a, b, c]```，你的正确输出应该是：[a, b, c]"
              f"下面是本次的待检查内容：【{children_nodes}】")
    logger.info(f"\n提问：{prompt}\n")

    formatted_children_nodes = get_GPT_response(prompt)
    logger.info(f"\n回答：{formatted_children_nodes}\n")
    return formatted_children_nodes


# KG_edges_file_path: 要加载的KG边文件路径，默认加载KG_seed
# KG_nodes_file_path: 要加载的KG节点文件路径，默认加载KG_seed
# KG_queue_file_path: 要加载的KG队列文件路径，默认为空
def load_KG(KG_edges_file_path="data/KG_seed/edges.json", KG_nodes_file_path="data/KG_seed/nodes.json",
            KG_queue_file_path=""):
    # 加载KG边
    with open(KG_edges_file_path, 'r', encoding='utf-8') as KG_edges_file:
        KG_edges_list = json.load(KG_edges_file)
        # 将【列表的列表】转换为【三元组的集合】，方便去重
        KG_edges = set()
        for KG_edge in KG_edges_list:
            KG_edge = tuple(KG_edge)
            KG_edges.add(KG_edge)
    logger.info(f"\n------------------------------KG边集合加载完成---------------------------\n")

    # 加载KG节点
    with open(KG_nodes_file_path, 'r', encoding='utf-8') as KG_nodes_file:
        KG_nodes_list = json.load(KG_nodes_file)
        # 将列表转换为集合，方便去重
        KG_nodes = set(KG_nodes_list)
    logger.info(f"\n------------------------------KG节点集合加载完成---------------------------\n")

    # KG队列默认为空
    KG_queue = []
    if KG_queue_file_path != "":
        # 如果有，则加载KG队列
        with open(KG_queue_file_path, 'r', encoding='utf-8') as KG_queue_file:
            KG_queue = json.load(KG_queue_file)
    logger.info(f"\n------------------------------KG队列加载完成---------------------------\n")

    return KG_edges, KG_nodes, KG_queue  # 返回2个集合，1个列表


# 检查节点有效性
def check_node_validity(node):
    logger.info(f"\n------------------------------开始检查节点：{node} 的有效性---------------------------\n")

    check_list = [
        f"“{node}“是否是一个指代Linux内核本身的概念（如：”Linux“、”Linux内核“）？如果是，返回”Yes“；如果不是，返回”No“。",
        f"”{node}“是否是一个与Linux内核无关的概念（如：“一个”、“所有”、“作者”、”技术“、”知识“、“操作”）？如果是，返回”Yes“；如果不是，返回”No“。"]

    for check_item in check_list:
        prompt = (f"假设你是一名操作系统专家，擅长Linux内核相关知识。"
                  f"请你回答：{check_item}"
                  f"请严格返回“Yes”或者“No”，不要返回任何其余内容。")
        logger.info(f"\n提问：{prompt}\n")

        check_res = get_GPT_response(prompt)
        logger.info(f"\n回答：{check_res}\n")

        check_prompt = (f"假设你是一个格式检查员，请你检查下面【】中的字符串内容是否等于“Yes”或者“No”。"
                        f"如果等于“Yes”或者“No”，则严格原样返回该字符串，不要返回任何其他内容。"
                        f"如果既不等于“Yes”也不等于“No”，那么请你判断字符串内容表达的意思是“Yes”还是“No”，并严格返回“Yes”或者“No”，不要返回任何其他内容。"
                        f"【{check_res}】")
        logger.info(f"\n提问：{check_prompt}\n")

        formatted_check_res = get_GPT_response(check_prompt)
        logger.info(f"\n回答：{formatted_check_res}\n")

        if formatted_check_res in ("Yes", "“Yes”"):
            logger.info(f"\n该概念无效\n")
            return False  # 该概念无效

    logger.info(f"\n该概念有效\n")
    return True  # 三条检查均通过，该概念有效。


# 检查逻辑关系正确性
def check_edge_correctness(node_A, relation_type, node_B):
    logger.info(
        f"\n------------------------------开始检查边：<{node_A}, {relation_type}, {node_B}> 的逻辑关系正确性---------------------------\n")

    relation_to_prompt = {"是一种": f"”{node_B}“是”{node_A}“的一种。例如："
                                    "【页表】是【数据结构】的一种。"
                                    "【分页】是【内存管理算法】的一种。"
                                    "【交换缓存】是【内存读取优化】的一种。"
                                    "【内存管理算法】是【算法】的一种。"
                                    "【LRU】是【页面置换算法】的一种。"
                                    "【FIFO】是【页面置换算法】的一种。"
                                    "【多级页表】是【页表查询优化】的一种。",
                          "是其中一方面": f"”{node_B}“是”{node_A}“的其中一方面。例如："
                                          "【内存监控与统计】是【内存管理】的其中一方面。"
                                          "【内存读取优化】是【内存管理】的其中一方面。"
                                          "【页面分配】是【页面管理】的其中一方面。"
                                          "【页面置换】是【页面管理】的其中一方面。",
                          "是其中一部分": f"“{node_B}”是“{node_A}“的其中一部分。例如："
                                          "【栈区】是【进程地址空间】的其中一部分。"
                                          "【堆区】是【进程地址空间】的其中一部分。",
                          "组成": f"“{node_A}”组成了“{node_B}”。例如："
                                  "【页】组成了【页表】。"
                                  "【页】组成了【虚拟内存空间】。"
                                  "【页】组成了【物理内存空间】。",
                          "需要使用": f"“{node_B}”需要使用“{node_A}”。例如："
                                      "【内存管理】需要使用【内存管理算法】。"
                                      "【页面置换】需要使用【页面置换算法】。"
                                      "【共享内存】需要使用【进程同步机制】。"
                                      "【共享内存】需要使用【共享内存文件系统】。"
                                      "【进程调度】需要使用【调度器】。",
                          "是对象": f"“{node_B}”是“{node_A}”的动作对象。例如："
                                    "【页】是【分页】的对象。"
                                    "【页】是【页面管理】的对象。"
                                    "【虚拟内存空间】是【内存管理】的对象。",
                          "实现基础": f"“{node_A}”是“{node_B}”的实现基础。例如："
                                      "【分页】是【交换缓存】的实现基础。"
                                      "【分页】是【页面管理】的实现基础。"
                                      "【虚拟内存文件系统】是【共享内存文件系统】的实现基础。",
                          "完成": f"“{node_B}”完成“{node_A}”。例如："
                                  "【内存映射单元】完成【地址映射】。"
                                  "【CPU】完成【进程调度】。",
                          "是属性": f"“{node_B}”是“{node_A}”的一类属性。例如："
                                    "【进程优先级】是【进程】的一类属性。"
                                    "【进程状态】是【进程】的一类属性。"}
    # flag = 0  # 防止死循环
    # while flag < 100:
    #     flag += 1
    prompt = (f"假设你是一名操作系统专家，擅长Linux内核相关知识。"
              f"请你判断下面的说法是否正确（两个节点之间的关系是否表述准确）：{relation_to_prompt[relation_type]}"
              f"如果两个节点之间的关系表述准确，则仅返回”Yes“，不要返回其它内容。"
              f"如果两个节点之间的关系表述不准确，则仅返回”No“，不要返回其它内容。")
    logger.info(f"\n提问：{prompt}\n")

    check_res = get_GPT_response(prompt)
    logger.info(f"\n回答：{check_res}\n")

    if check_res in ("Yes", "”Yes“"):
        logger.info(f"\n逻辑关系正确。\n")
        return True  # 逻辑关系准确，直接返回
    else:
        # TODO：逻辑关系不准确，是否需要重新给GPT生成？
        logger.info(f"\n逻辑关系错误。\n")
        return False


# 语义去重。
def deduplication(node):
    pass


# 遍历所有逻辑关系，扩展节点
def expand_node(node):
    relation_to_prompt = {"是一种": f"“某个概念”是”{node}“的一种。例如："
                                    "【页表】是【数据结构】的一种。"
                                    "【分页】是【内存管理算法】的一种。"
                                    "【交换缓存】是【内存读取优化】的一种。"
                                    "【内存管理算法】是【算法】的一种。"
                                    "【LRU】是【页面置换算法】的一种。"
                                    "【FIFO】是【页面置换算法】的一种。"
                                    "【多级页表】是【页表查询优化】的一种。",
                          "是其中一方面": f"“某个概念”是”{node}“的其中一方面。例如："
                                          "【内存监控与统计】是【内存管理】的其中一方面。"
                                          "【内存读取优化】是【内存管理】的其中一方面。"
                                          "【页面分配】是【页面管理】的其中一方面。"
                                          "【页面置换】是【页面管理】的其中一方面。",
                          "是其中一部分": f"“某个概念”是“{node}“的其中一部分。例如："
                                          "【栈区】是【进程地址空间】的其中一部分。"
                                          "【堆区】是【进程地址空间】的其中一部分。",
                          "组成": f"“某个概念”组成了“{node}”。例如："
                                  "【页】组成了【页表】。"
                                  "【页】组成了【虚拟内存空间】。"
                                  "【页】组成了【物理内存空间】。",
                          "需要使用": f"“某个概念”需要使用“{node}”。例如："
                                      "【内存管理】需要使用【内存管理算法】。"
                                      "【页面置换】需要使用【页面置换算法】。"
                                      "【共享内存】需要使用【进程同步机制】。"
                                      "【共享内存】需要使用【共享内存文件系统】。"
                                      "【进程调度】需要使用【调度器】。",
                          "是对象": f"“某个概念”是“{node}”的动作对象。例如："
                                    "【页】是【分页】的对象。"
                                    "【页】是【页面管理】的对象。"
                                    "【虚拟内存空间】是【内存管理】的对象。",
                          "实现基础": f"“某个概念”是基于“{node}”实现的。例如："
                                      "【交换缓存】是基于【分页】实现的。"
                                      "【页面管理】是基于【分页】实现的。"
                                      "【共享内存文件系统】是基于【虚拟内存文件系统】实现的。",
                          "完成": f"“某个概念”完成“{node}”。例如："
                                  "【内存映射单元】完成【地址映射】。"
                                  "【CPU】完成【进程调度】。",
                          "是属性": f"“某个概念”是“{node}”的一类属性。例如："
                                    "【进程优先级】是【进程】的一类属性。"
                                    "【进程状态】是【进程】的一类属性。"}

    res_dict = {}
    # 遍历所有逻辑类型
    for relation_type in relation_types:
        # 待拼接的部分prompt
        relation_prompt = relation_to_prompt[relation_type]
        prompt = (f"假设你是一名操作系统专家，擅长Linux内核相关知识。"
                  f"请你回答：在Linux内核概念中，是否存在某些概念，与概念“{node}”满足如下关系：{relation_prompt} "
                  f"如果有恰当的符合关系的概念，则将这些概念放入一个Python列表中，严格以Python列表的形式返回。"
                  f"如果没有恰当的符合关系的概念，则仅返回一个空Python列表。"
                  f"注意：列表中的元素应当是“某个概念”，而不是一个句子。"
                  f"请严格按照格式返回内容，不要返回任何其它内容。")
        logger.info(f"\n提问：{prompt}\n")

        children_nodes = get_GPT_response(prompt)
        logger.info(f"\n回答：{children_nodes}\n")

        # 检查children_nodes格式是否正确，若不正确，重新返回GPT处理
        formatted_children_nodes = check_format(children_nodes)
        res_dict[relation_type] = json.loads(formatted_children_nodes)

    return res_dict  # 返回格式严格的所有节点列表


# seed_queue: bfs队列，默认为空
# top_nodes_num: 扩展多少个节点就停止，默认100
def bfs_expand(queue, max_nodes_num=100):
    current_nodes_num = 0  # 当前已经扩展的节点数量

    # 停止条件：节点数量达到限制 or 队列中已经没有新节点了
    while current_nodes_num < max_nodes_num and len(queue) > 0:
        top_node = queue[0]  # 取出队头节点: 本轮扩展节点
        queue = queue[1:]  # 出队列
        logger.info(f"\n------------------------------本轮扩展节点：{top_node}---------------------------\n")

        # 扩展top_nodes, 得到各种逻辑关系的子节点列表
        children_nodes_dict = expand_node(top_node)
        # 遍历所有逻辑关系，将子节点列表入队列
        for relation_type in relation_types:
            children_nodes = children_nodes_dict[relation_type]
            # 逐一检查子节点，入队尾
            for children_node in children_nodes:
                # 节点有效性检查
                if check_node_validity(children_node) == False:
                    logger.info(f"\n丢弃该节点：{children_node}\n")
                    break
                # 逻辑关系正确性检查
                if check_edge_correctness(top_node, relation_type, children_node) == False:
                    logger.info(f"\n丢弃该节点：{children_node}\n")
                    break
                # 若文本无重复，则入队列，继续扩展
                if children_node not in KG_nodes:
                    queue.append(children_node)
                    current_nodes_num += 1  # 每次有节点入队，节点数量+1
                    logger.info(
                        f"\n------------------------------加入队列：{children_node}---------------------------\n")
                # <children_node, relation_type, top_node> 加入KG
                KG_edges.add((children_node, relation_type, top_node))  # 向边集合中加入三元组
                KG_nodes.add(children_node)  # 向节点集合中加入新节点
                logger.info(
                    f"\n------------------------------加入KG：<{top_node}, {relation_type}, {children_node}>---------------------------\n")

    return queue  # 停止之后，返回当前queue，保存为checkpoint


# 获取当前日期和时间
now = datetime.now()
# 格式化日期和时间
formatted_time = now.strftime("%Y-%m-%d--%H-%M-%S")

# 日志设置
logger = logging.getLogger('test')
logger.setLevel(level=logging.DEBUG)
handler = logging.FileHandler(
    f"data/log/{formatted_time}.txt")
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('')
handler.setFormatter(formatter)

console = logging.StreamHandler()
console.setLevel(logging.DEBUG)

logger.addHandler(handler)
logger.addHandler(console)

# 所有逻辑关系类型
relation_types = ["是一种", "是其中一方面", "是其中一部分",
                  "组成", "需要使用", "是对象", "实现基础",
                  "完成", "是属性"]

# 加载KG checkpoint
KG_edges, KG_nodes, KG_queue = load_KG()

if __name__ == '__main__':
    # BFS扩展，更新KG_edges, KG_nodes, KG_queue
    KG_queue = list(KG_nodes)  # 特殊情况：从seed直接开始扩展时，要将nodes加入queue
    KG_queue = bfs_expand(KG_queue, 50)
    logger.info('\n------------------------------开始用BFS扩展KG---------------------------\n')

    # 将每条边【从三元组转换为列表】，便于json存储
    list_KG_edges = []
    for tuple_KG_edge in KG_edges:
        list_KG_edge = list(tuple_KG_edge)
        list_KG_edges.append(list_KG_edge)
    # 将节点集合转换为列表，便于json存储
    list_KG_nodes = list(KG_nodes)

    # 用json格式存储checkpoint
    logger.info('\n------------------------------开始存储KG checkpoint---------------------------\n')
    with open(f"data/KG_checkpoint/{formatted_time}_KG_edges.json", 'w') as KG_edges_file:
        json.dump(list_KG_edges, KG_edges_file, ensure_ascii=False)
    with open(f"data/KG_checkpoint/{formatted_time}_KG_nodes.json", 'w') as KG_nodes_file:
        json.dump(list_KG_nodes, KG_nodes_file, ensure_ascii=False)
    with open(f"data/KG_checkpoint/{formatted_time}_KG_queue.json", 'w') as KG_queue_file:
        json.dump(KG_queue, KG_queue_file, ensure_ascii=False)

    # 写入csv文件，用于neo4j可视化
    with open(f"data/KG_checkpoint/{formatted_time}_CSV.csv", mode="w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["node_A", "relation_type", "node_B"])  # 写入标题行
        writer.writerows(list_KG_edges)  # 写入数据行

    logger.info('\n------------------------------扩展结束---------------------------\n')

