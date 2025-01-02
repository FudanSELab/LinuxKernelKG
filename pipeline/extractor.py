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
                
                # 获取commits
                commit_ids = self.db.get_commits_by_feature(feature_id)
                commits = []
                for commit_id in commit_ids:
                    commit = self._get_commit(commit_id)
                    commits.append(commit)
                
                # 添加日志记录commits数量
                self.logger.info(f"Processing index={index+1}/{len(features)}, feature_id {feature_id} with {len(commits)} commits")
                
                # 简单的分组处理，无论commits数量多少
                for i in range(0, len(commits), 5):
                    commits_group = "\n".join(commits[i:i+5])
                    
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
                
                    commits_group_extracted = {
                        "feature_id": feature_id,
                        "feature_description": feature_description,
                        "version": version,
                        "commit_ids": commit_ids[i:i+5],
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

    def _get_commit(self, commit_id):
        """查询数据库或者爬网页来获取某个 commit 的 subject 和 message"""
        commit = self.db.get_commits_info([commit_id])
        if not commit:
            commit = self._curl_commit(commit_id)
            self.db.insert_commit_info(commit_id, commit["commit_subject"], commit["commit_message"])
            commit = f"commit_subject:\n{commit['commit_subject']}\ncommit_message:\n{commit['commit_message']}\n"
        else:
            commit = commit[0]
        return commit
    
    def _curl_commit(self, commit_id):
        """访问 linux 仓库获取 commit 信息"""
        url = f'https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id={commit_id}'
        
        # 重试机制
        for _ in range(self.config.MAX_RETRIES):
            try:
                response = requests.get(url)
                soup = BeautifulSoup(response.text, 'html.parser')
                commit_subject = soup.find('div', class_='commit-subject').text
                commit_msg = soup.find('div', class_='commit-msg').text
                commit_msg = self._clean_commit_message(commit_msg)
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
    
    def _clean_commit_message(message):
        """清洗 commit message, 去掉指定前缀的行"""
        lines = message.split('\n')
        prefixes_to_remove = ['Cc:', 'Link:', 'Signed-off-by:', 'Tested-by:', 'Acked-by:', 'Reported-by:', 'Suggested-by', 'Co-developed-by', 'Reviewed-by']
        filtered_lines = [line for line in lines if not any(line.strip().startswith(prefix) for prefix in prefixes_to_remove)]
        return '\n'.join(filtered_lines)