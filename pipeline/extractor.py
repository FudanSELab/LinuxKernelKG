from bs4 import BeautifulSoup
import requests
from prompts.extractEntity import extractEntityPrompt
from prompts.extractTriple import extractTriplePrompt
from prompts.extractTripleOpen import extractTripleOpenPrompt
from prompts.verify import verifyPrompt
from utils.deepseek import deepseek
from utils.utils import *
import json
import time
from utils.logger import setup_logger
from utils.db import DB
def strip_json(text):
    """
    从文本中提取JSON字符串并清理
    Args:
        text: 包含JSON的文本
    Returns:
        清理后的JSON字符串
    """
    # 找到第一个 { 和最后一个 } 的位置
    start = text.find('{')
    end = text.rfind('}')
    
    if start == -1 or end == -1:
        raise ValueError("No valid JSON found in the text")
        
    # 提取JSON部分
    json_str = text[start:end + 1]
    
    try:
        # 验证是否为有效的JSON
        json.loads(json_str)
        return json_str
    except json.JSONDecodeError:
        # 如果解析失败，尝试进一步清理
        # 移除可能的多行注释、空行等
        lines = json_str.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('//') and not line.startswith('/*'):
                cleaned_lines.append(line)
        cleaned_json = ' '.join(cleaned_lines)
        return cleaned_json

class EntityRelationExtractor:
    def __init__(self, config):
        self.logger = setup_logger(name="EntityRelationExtractor", level="INFO")
        self.llm = deepseek()
        self.config = config
        self.db = DB(config)

    def extract_entities_and_relations(self, features, save_to_file=False):
        """
        抽取实体和关系。
        Args:
            features: list of dict, 每个 dict 包含 feature_id, feature_description 和 version
        Returns:
            features_output: list of dict, 每个 dict 包含 feature_id, feature_description, version, commit_ids, entities 和 triples
        """
        try:
            features_output = []
            for index, feature in enumerate(features):
                feature_id = feature['feature_id']
                feature_description = feature['feature_description']
                version = feature['version']
                
                # 注释掉获取commits的逻辑
                # commit_ids = self.db.get_commits_by_feature(feature_id)
                # commits = []
                # for commit_id in commit_ids:
                #     commit = self._get_commit(commit_id)
                #     commits.append(commit)
                
                self.logger.info(f"Processing index={index+1}/{len(features)}, feature_id {feature_id}")
                # # 简单的分组处理，无论commits数量多少
                # for i in range(0, len(commits), 5):
                #     commits_group = "\n".join(commits[i:i+5])
                # 使用空字符串替代commits
                commits_group = ""
                
                # 实体抽取
                prompt_entity = extractEntityPrompt(
                    feature_description=feature_description, 
                    commits=commits_group
                ).format()
                response_entity = self.llm.get_response(prompt_entity)
                object_entity = json.loads(strip_json(response_entity))
                
                # TODO: 关系抽取需要取消注释
                # 关系抽取
                # prompt_triple = extractTriplePrompt(
                #     feature_description=feature_description, 
                #     commits=commits_group
                # ).format()
                # response_triple = self.llm.get_response(prompt_triple)
                # object_triple = json.loads(strip_json(response_triple))
                
                # # 开放关系抽取
                # prompt_tripleOpen = extractTripleOpenPrompt(
                #     feature_description=feature_description, 
                #     commits=commits_group
                # ).format()
                # response_tripleOpen = self.llm.get_response(prompt_tripleOpen)
                # object_tripleOpen = json.loads(strip_json(response_tripleOpen))
                
                # # 合并三元组
                # all_triples = object_triple['triples'] + object_tripleOpen['triples']
                
                # # 验证
                # prompt_verify = verifyPrompt(
                #     feature_description=feature_description,
                #     commits=commits_group,
                #     entities=object_entity['entities'],
                #     triples=all_triples
                # ).format()
                # try:
                #     response_verify = self.llm.get_response(prompt_verify)
                #     json_str = strip_json(response_verify)
                #     object_verify = json.loads(json_str)
                # except json.JSONDecodeError as e:
                #     self.logger.error(f"Failed to parse JSON response: {e}")
                #     self.logger.debug(f"Raw response: {response_verify}")
                #     object_verify = {"entities": [], "triples": []}

                # TODO: 验证需要取消注释
                object_verify = {"entities": [], "triples": []}
                
                commits_group_extracted = {
                    "feature_id": feature_id,
                    "feature_description": feature_description,
                    "version": version,
                    "commit_ids": [],  # 空列表替代原来的commit_ids
                    "entities": object_entity['entities'],
                    "triples": object_verify['triples']
                }
                
                features_output.append(commits_group_extracted)

                if save_to_file:
                    with open(f"data/features/features_output_20250102.json", 'w') as f:
                        json.dump(features_output, f, ensure_ascii=False, indent=4)
                    
            return features_output
        
        except Exception as e:
            self.logger.error(f"Failed to extract entities and relations: {e}")
            raise e