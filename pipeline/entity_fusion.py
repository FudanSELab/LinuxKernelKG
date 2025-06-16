from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from utils.logger import setup_logger
from utils.deepseek import deepseek
from utils.fusion_cache import FusionCache
import requests
import pandas as pd
import asyncio
import re
import aiohttp
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from utils.name_handler import NameHandler
from selenium.common.exceptions import TimeoutException, WebDriverException
import concurrent.futures
from functools import partial
import time
from models.entity import Entity
import json
from utils.utils import strip_json

class EntityFusion:
    def __init__(self, config):
        self.logger = setup_logger('entity_fusion', file_output=True)
        self.config = config
        self.fusion_cache = FusionCache()
        self.llm = deepseek()
        self.name_handler = NameHandler.get_inst()
        self.persistence_path = getattr(config, 'fusion_persistence_path', 'data/fused_entities')
        self.persistence_interval = getattr(config, 'fusion_persistence_interval', 30)  # 默认3分钟
        self.last_persistence_time = 0
        self.fused_entities_by_class = self._load_persisted_entities()  
        self.aiohttp_retry_attempts = getattr(config, 'aiohttp_retry_attempts', 3)
        self.aiohttp_retry_delay = getattr(config, 'aiohttp_retry_delay', 2) # 秒

        # Kernel Docs并发控制
        self.kernel_docs_concurrency = getattr(config, 'kernel_docs_concurrency', 2) #默认2个并发
        self.kernel_docs_semaphore = asyncio.Semaphore(self.kernel_docs_concurrency)

        # 启动定期保存任务
        self._start_persistence_timer()

    async def process_fusion(self, entities, linked_entities=[]):
        """处理实体融合的主流程
        
        Args:
            entities (list): 需要进行融合的实体列表
            linked_entities (list, optional): 成功链接到Wikipedia的实体列表
        Returns:
            list: 包含融合组的列表，每个融合组包含原始实体和其别名
        """

        # 1. 查找引用源 - 分离有引用源和无引用源的实体
        self.logger.info("查找实体的外部引用源")
        for entity in entities:
            entity_name = entity.name
            variations = await self._generate_variations(entity_name, entity.context, entity.feature_id)
            # 引用源验证
            for variation in variations:
                reference = await self._find_entity_reference(
                    variation,
                    entity.feature_id,
                    entity.commit_ids,
                    entity.version,
                )
                # 如果reference不为空，则将reference添加到entity.external_links中
                if reference:
                    # 给reference里添加key是variation，value是variation的具体值
                    for ref in reference:
                        ref['variation'] = variation
                    entity.external_links = reference
                    break
        
        entities_with_refs = [entity for entity in entities if entity.external_links]
        # 保存有引用源的实体到JSON文件
        entities_with_refs_file = "output/entity_fusion/entities_with_refs_mm_0601.json"
        
        # 确保输出目录存在
        import os
        output_dir = os.path.dirname(entities_with_refs_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # 将实体转换为字典格式并保存
        entities_with_refs_dicts = [entity.to_dict() for entity in entities_with_refs]
        
        with open(entities_with_refs_file, 'w', encoding='utf-8') as f:
            json.dump(entities_with_refs_dicts, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"已保存 {len(entities_with_refs)} 个有引用源的实体到 {entities_with_refs_file}")

        # 利用优化后的tf-idf算法过滤一些大众化的词

        # 分析bootlin的返回结果，提取代码上下文，与术语的上下文对比后判断是否要建立映射关系。

        
        # 退出程序
        import sys
        sys.exit(0)

        # 2. 准备融合池 - 合并有引用的新实体和已链接实体，并按类别分类
        self.logger.info("准备融合池，合并有引用的新实体和已链接实体")

        start_time = time.time()
        fusion_pool_by_class = self._prepare_fusion_pool_by_class(linked_entities, entities_with_refs)
        self.logger.info(f"融合池准备完成，耗时: {time.time() - start_time:.2f}秒")
        
        # 3. 执行基于规则的融合 - 对每个类别分别进行融合，并与已有融合实体进行融合
        self.logger.info("执行基于规则的融合")
        start_time = time.time()
        fusion_groups = self._perform_rule_based_fusion(fusion_pool_by_class)
        self.logger.info(f"基于规则的融合完成，耗时: {time.time() - start_time:.2f}秒")

        # 直接从JSON文件读取fusion_groups
        # fusion_groups_file_path = "output/entity_fusion/fused_entities_result_mm_0510.json"
        # self.logger.info(f"Attempting to load fusion_groups from {fusion_groups_file_path}")
        # fusion_groups = []
        # try:
        #     with open(fusion_groups_file_path, 'r', encoding='utf-8') as f:
        #         loaded_data = json.load(f)
            
        #     if isinstance(loaded_data, list):
        #         for entity_dict in loaded_data:
        #             try:
        #                 # Entity class is imported at the top of the file
        #                 fusion_groups.append(Entity.from_dict(entity_dict))
        #             except Exception as e_conv:
        #                 self.logger.error(f"Error converting dict to Entity: {entity_dict}, error: {e_conv}")
        #     else:
        #         self.logger.error(f"Expected a list from {fusion_groups_file_path}, got {type(loaded_data)}. fusion_groups will be empty.")
        # except FileNotFoundError:
        #     self.logger.error(f"File {fusion_groups_file_path} not found. fusion_groups will be empty.")
        # except json.JSONDecodeError as e_json:
        #     self.logger.error(f"Error decoding JSON from {fusion_groups_file_path}: {e_json}. fusion_groups will be empty.")
        # except Exception as e_gen: # Catch other potential errors during file operations or unexpected issues
        #     self.logger.error(f"An unexpected error occurred while loading {fusion_groups_file_path}: {e_gen}. fusion_groups will be empty.")
        
        # self.logger.info(f"Successfully loaded {len(fusion_groups)} entities into fusion_groups from {fusion_groups_file_path if 'fusion_groups_file_path' in locals() else 'configured path'}")
         # 直接从JSON文件读取fusion_groups

        # 4. 执行基于 LLM 的补充融合
        self.logger.info(f"执行基于 LLM 的补充融合，输入 {len(fusion_groups)} 个规则融合组")
        start_llm_time = time.time()
        final_fusion_result = await self._perform_llm_based_fusion(fusion_groups)
        self.logger.info(f"基于 LLM 的补充融合完成，耗时: {time.time() - start_llm_time:.2f}秒. 输出 {len(final_fusion_result)} 个融合组")
        
        return final_fusion_result


    # @FusionCache.cached_operation('variations')
    async def _generate_variations(self, mention: str,context: str = None, feature_id: str = None) -> List[str]:
        """生成术语的变体
        
        Args:
            mention: 需要生成变体的术语
            feature_id: 特征ID，用于缓存
            commit_ids: 提交ID列表，用于缓存
            
        Returns:
            List[str]: 生成的变体列表
        """
        # 只需要实现实际的获取逻辑
        prompt = self._create_variation_prompt(mention, context)
        response = self._get_llm_response(prompt)
        variations = self._parse_variations_response(response, mention)
        variations.append(mention)
        variations = list(dict.fromkeys(variations))
        return variations

    def _prepare_fusion_pool_by_class(self, linked_entities, entities_with_refs):
        """准备融合池，合并已链接实体和有引用的新实体，并按类别分类
        
        Args:
            linked_entities (list): 已链接到Wikipedia的实体列表
            entities_with_refs (list): 有外部引用的实体列表
            
        Returns:
            dict: 按实体类别分类的融合池
        """
        self.logger.info(f"准备融合池: {len(linked_entities)}个已链接实体, {len(entities_with_refs)}个引用实体")
        
        # 使用字典来按类别跟踪实体
        fusion_pool_by_class = {class_name: [] for class_name in Entity.ENTITY_TYPES}
        
        # 处理所有实体，先处理linked_entities保证优先级
        for entity in linked_entities + entities_with_refs:
            entity_type = entity.entity_type
            fusion_pool_by_class[entity_type].append(entity)
        
        self.logger.info(f"融合池按类别分类完成")
        
        return fusion_pool_by_class

    def _perform_rule_based_fusion(self, fusion_pool_by_class):
        """执行基于规则的融合，识别同一实体的不同表示形式，并与已有融合实体进行融合
        
        Args:
            fusion_pool_by_class (dict): 按实体类别分类的融合池
            
        Returns:
            list: 融合组列表，每个融合组是一个包含关联实体的列表
        """
        all_fusion_groups = []
        # 获取名称处理器
        name_handler = self.name_handler
        # 对每个类别分别进行融合
        for class_name, new_entities in fusion_pool_by_class.items():
            self.logger.info(f"开始融合 {class_name} 类别，共有 {len(new_entities)} 个新实体和 {len(self.fused_entities_by_class[class_name])} 个已存在实体")
            
            # 合并新实体和已存在的该类别融合实体
            combined_entities = new_entities + self.fused_entities_by_class[class_name]
            
            # 直接使用集合记录别名关系，每个集合包含互为别名的实体ID
            fusion_groups = []
            entity_to_group = {}  # 记录每个实体ID所在的组索引
            
            # 比较新实体和所有实体
            for entity2 in new_entities:
                found_match = False
                
                # 检查entity2是否可以与任何已有组合并
                for entity1 in combined_entities:
                    name1, name2 = entity1.name, entity2.name

                    # 应用融合规则
                    if name1 == name2 or name_handler.check_abbr(name1, name2) or self._check_singular_plural_relation(name1, name2) \
                        or self._check_gerund_relation(name1, name2) or self._check_naming_convention_relation(name1, name2) \
                        or entity1.is_same_wikipedia_link(entity2):
                        found_match = True
                        if entity1.id == entity2.id:
                            continue
                        combined_entities.remove(entity2)
                        new_entities.remove(entity2)
                        # 按照url_type将entity2合并进entity1的外部链接列表,并去重
                        entity1.merge_with(entity2)
                        break
            
            # 更新已存在融合实体
            self.fused_entities_by_class[class_name] = combined_entities # 每个组选第一个实体作为代表
            
            self.logger.info(f"{class_name} 类别融合完成，识别出 {len(combined_entities)} 个融合组")
        
        self.logger.info(f"所有类别融合完成，总共 {len(new_entities)} 个融合组")
        
        return new_entities

    # async def _find_entity_references(self, entities):
    #     entities_with_refs = {}
    #     entities_without_refs = {}

    #     for entity in entities:
    #         entity_name = entity.name
    #         entity_key = self._create_entity_key(
    #             entity,
    #             entity.feature_id,
    #             entity.commit_ids
    #         )

    #         # 引用源验证
    #         reference = await self._find_entity_reference(
    #             entity,
    #             entity.feature_id,
    #             entity.commit_ids,
    #         )
            # entity.external_links = reference
        
    @FusionCache.cached_operation('candidates')
    async def _generate_candidates(self, entity, feature_id=None):
        """生成实体的候选变体
        
        结合规则和大模型方式生成变体：
        1. 使用规则处理基本的命名风格转换
        2. 使用大模型处理复杂的缩写形式
        """
        candidates = set([entity])  
        
        # 1. 使用规则处理基本命名风格
        candidates.update(self._generate_naming_variants(entity))
        
        # 2. 使用大模型处理复杂缩写：语义层面的融合可以先不考虑
        # abbreviation_variants = await self._generate_abbreviation_variants(entity)
        # candidates.update(abbreviation_variants)
        
        # 移除无效候选项
        candidates.discard('')
        candidates.discard(None)
        
        return list(candidates)

    def _get_llm_response(self, prompt: str) -> str:
        """获取LLM的响应"""
        try:
            # 调用 LLM 获取响应
            response = self.llm.get_response(prompt)
            
            if not response:
                raise ValueError("Empty response received from LLM")
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error getting LLM response: {str(e)}")
            raise  # 重新抛出异常，让调用方处理

    @FusionCache.cached_operation('reference')
    async def _find_entity_reference(self, entity_name, feature_id=None, commit_ids=None, version='latest'):
        """查找实体的引用源（官方文档或代码）
        
        Args:
            entity (str): 主要实体名称
            feature_id (str, optional): 特征ID
            commit_ids (list, optional): 提交ID列表
            
        Returns:
            dict: 包含实体引用信息的字典
        """
        try:
            # 对所有候选项并行执行搜索
            search_tasks = []
            search_tasks.extend([
                self._search_bootlin(entity_name, version),
                # self._search_kernel_docs(entity.name)
            ])
            
            # 并行执行所有搜索任务
            all_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            # 过滤和整理结果
            valid_references = []
            for result in all_results:
                if isinstance(result, Exception):
                    continue
                if result:  # 如果结果有效
                    valid_references.append(result)
                    # entity.add_external_link(result['url_type'], result['url'])
            
            # 返回统一格式的结果
            # 例如:
            #[
            #         {
            #             'reference_type': 'code',
            #             'references': ['https://elixir.bootlin.com/linux/v6.12.6/A/ident/kvm_vcpu_block']
            #         },
            #         {
            #             'reference_type': 'documentation', 
            #             'references': ['https://www.kernel.org/doc/html/latest/virt/kvm/api.html#kvm-vcpu-block']
            #         }
            #]
            return valid_references
            
        except Exception as e:
            self.logger.error(f"Error finding reference for entity {entity}: {str(e)}")
            return [{'reference_type': f"error {str(e)}", 'references': []}]

    async def _search_bootlin(self, entity, version):
        """异步搜索Bootlin并返回结构化结果"""
        # 去除标识符末尾的括号
        if entity.endswith('()'):
            entity = entity[:-2]

        if version == '' or version is None:
            version = 'latest'
        else:
            version = f'v{version}'

        base_url = f'https://elixir.bootlin.com/linux/{version}/A/ident/'
        # base_url = f'http://10.176.37.1:6106/linux/{version}/A/ident/'
        headers = {
            'User-Agent': 'Chrome/90.0.4430.93 Safari/537.36'
        }
        

        # 尝试下划线格式搜索
        underscored_entity = '_'.join(entity.split())
        # if underscored_entity != entity:  # 只有当下划线格式与原始格式不同时才尝试
        url = f"{base_url}{underscored_entity}"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            print(f'在 Bootlin 找到与 "{underscored_entity}" 相关的结果。')
            return {
                'url_type': 'code',
                'url': [url]
            }
        else:
            print(f'Bootlin 搜索失败，状态码: {response.status_code}, 实体: {entity}')
        
        return None

    async def _search_kernel_docs(self, entity):
        """搜索 Kernel Docs 文档引用
        
        Args:
            entity (str): 要搜索的实体名称
            
        Returns:
            dict: 包含引用信息的字典，如果未找到则返回None
        """
        async with self.kernel_docs_semaphore:
            self.logger.info(f"Acquired semaphore for {entity}, remaining: {self.kernel_docs_semaphore._value}/{self.kernel_docs_concurrency}")
            base_url = 'https://docs.kernel.org/search.html?q='
            
            # 配置 Chrome 选项，增加了 disable-gpu、固定窗口大小和远程调试端口等参数
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-setuid-sandbox')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--log-level=3')
            chrome_options.add_argument('--silent')
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

            driver = None
            try:
                self.logger.info(f"开始搜索 {entity}...")
                driver = webdriver.Chrome(options=chrome_options)
                url = f"{base_url}{entity}"
                driver.get(url)

                # 设置等待时间，并等待 search-summary 元素出现
                wait = WebDriverWait(driver, 6)
                search_summary_element = wait.until(
                    EC.presence_of_element_located((By.CLASS_NAME, "search-summary"))
                )
                # 获取 search-summary 的文本内容
                search_summary = search_summary_element.text
                # 打印 search-summary 的内容到控制台
                print("Search Summary:", search_summary)
                
                if "did not match any documents" in search_summary:
                    self.logger.info(f'在 Kernel Docs 没有找到与 "{entity}" 相关的结果。')
                    return None

                references = []
                # 修改：使用正确的 class="search" 选择器定位 ul 元素
                try:
                    search_container = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "search"))
                    )
                    # 从 ul.search 中查找所有链接
                    links = search_container.find_elements(By.TAG_NAME, "a")
                except Exception as exc:
                    self.logger.warning(f"无法找到 class='search' 下的链接: {exc}. 尝试从整个页面查找链接。")
                    links = driver.find_elements(By.TAG_NAME, "a")

                for link in links:
                    try:
                        result_url = link.get_attribute('href')
                        if not result_url or not result_url.startswith('http'):
                            continue
                            
                        async with aiohttp.ClientSession() as session:
                            async with session.get(result_url) as response:
                                if response.status == 200:
                                    content = await response.text()
                                    # 使用业务逻辑判断实体是否在目标页面中，限制最多5个引用
                                    if entity.lower() in content.lower():
                                        references.append(result_url)
                                        self.logger.info(f'在 Kernel Docs 找到相关内容: {result_url}')
                                        # 当找到5个引用后停止搜索
                                        if len(references) >= 1:
                                            break
                    except Exception as e:
                        self.logger.warning(f"处理链接时出错: {str(e)}")
                        continue

                if references:
                    return {
                        'url_type': 'documentation',
                        'url': references
                    }
                else:
                    self.logger.info(f'在 Kernel Docs 没有找到与 "{entity}" 相关的内容。')
                    return None

            except TimeoutException:
                self.logger.warning(f'在 Kernel Docs 搜索超时: "{entity}"')
                return None
            except WebDriverException as e:
                self.logger.error(f"WebDriver错误: {str(e)}")
                return None
            except Exception as e:
                self.logger.error(f"搜索过程中发生错误: {str(e)}")
                return None
            finally:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                self.logger.info(f"Released semaphore for {entity}, remaining: {self.kernel_docs_semaphore._value + 1}/{self.kernel_docs_concurrency}") # _value is internal, but for logging

    def _create_entity_key(self, entity, feature_id, commit_ids):
        """创建实体的复合键
        
        Args:
            entity (Entity): 实体对象
            feature_id (str): 特征ID
            commit_ids (list): 提交ID列表
            
        Returns:
            str: 由实体名称、特征ID和提交ID组成的复合键
        """
        # 确保commit_ids是有序的
        commit_ids_str = ','.join(sorted(commit_ids)) if commit_ids else ''
        feature_id_str = str(feature_id) if feature_id else ''
        
        return f"{entity.name}_{feature_id_str}_{commit_ids_str}"

    def _normalize_fusion_groups(self, fusion_groups):
        """规范化融合组，选择规范形式和整理结果
        
        规范化规则:
        1. 使用空格作为连接符（而非下划线或连字符）
        2. 优先选择有外部引用的实体名称
        3. 其他条件相同时，选择最长的名称
        
        Args:
            fusion_groups (list): 融合组列表，每个融合组是一个包含关联实体的列表
            
        Returns:
            list: 规范化后的融合组列表
        """
        normalized_fusion_groups = []
        
        for group in fusion_groups:
                
            # 4. 规范化连接符为空格
            def normalize_name(name):
                # 驼峰转换: AbcDef -> Abc Def
                s1 = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
                # 替换所有连词符和下划线为空格
                s2 = re.sub(r'[-_]', ' ', s1)
                # 删除多余空格
                return re.sub(r'\s+', ' ', s2).strip()
            
            # 5. 最后选择最长的名称
            normalized_entity = max(group, key=lambda e: len(e.name))
            
            # 应用规范化名称
            normalized_entity.name = normalize_name(normalized_entity.name)
            
            # 将融合组中其他实体的名称添加为别名
            for entity in group:
                if entity.id != normalized_entity.id:
                    normalized_entity.add_alias(entity.name)
            
            normalized_fusion_groups.append(normalized_entity)
        
        return normalized_fusion_groups

    def _check_singular_plural_relation(self, name1, name2):
        """检查两个名称是否为单复数关系
        
        处理常见的英语单复数变化规则:
        - 一般情况: 加's' (file/files)
        - 以s, x, z, ch, sh结尾: 加'es' (bus/buses, box/boxes)
        - 以辅音+y结尾: 变y为i加es (facility/facilities)
        - 以o结尾的特殊情况: 加'es' (hero/heroes)
        - 不规则变化: 使用预定义映射 (man/men, child/children)
        
        Args:
            name1, name2: 要比较的两个名称
            
        Returns:
            bool: 如果两个名称是单复数关系，返回True
        """
        # 不规则复数形式映射
        irregular_plurals = {
            'man': 'men', 'woman': 'women', 'child': 'children',
            'person': 'people', 'foot': 'feet', 'tooth': 'teeth',
            'goose': 'geese', 'mouse': 'mice', 'ox': 'oxen',
            'datum': 'data', 'medium': 'media', 'analysis': 'analyses',
            'crisis': 'crises', 'phenomenon': 'phenomena', 'index': 'indices',
            'matrix': 'matrices', 'vertex': 'vertices', 'criterion': 'criteria'
        }
        
        # 标准化比较
        n1, n2 = name1.lower(), name2.lower()
        
        # 检查不规则复数
        for singular, plural in irregular_plurals.items():
            if (n1 == singular and n2 == plural) or (n1 == plural and n2 == singular):
                return True
        
        # 检查标准's'结尾的复数
        if n1.rstrip('s') == n2.rstrip('s') and n1.rstrip('s'):
            return True
        
        # 检查'es'结尾的复数
        if (n1.endswith('es') and n1[:-2] == n2) or (n2.endswith('es') and n2[:-2] == n1):
            return True
        
        # 检查辅音+y变为ies的情况
        if (n1.endswith('y') and n2.endswith('ies') and n1[:-1] == n2[:-3]) or \
           (n2.endswith('y') and n1.endswith('ies') and n2[:-1] == n1[:-3]):
            return True
        
        return False

    def _check_gerund_relation(self, name1, name2):
        """检查两个名称是否为动词原形和动名词关系
        
        处理常见的动名词变化:
        - 一般情况: 加'ing' (read/reading)
        - 以e结尾: 去e加ing (write/writing)
        - 短元音+辅音结尾: 双写辅音加ing (run/running)
        
        Args:
            name1, name2: 要比较的两个名称
            
        Returns:
            bool: 如果两个名称是动词原形和动名词关系，返回True
        """
        n1, n2 = name1.lower(), name2.lower()
        
        # 基本情况: 加ing
        if (n1.endswith('ing') and n1[:-3] == n2) or (n2.endswith('ing') and n2[:-3] == n1):
            return True
        
        # e结尾情况: 去e加ing
        if (n1.endswith('ing') and n2.endswith('e') and n1[:-3] == n2[:-1]) or \
           (n2.endswith('ing') and n1.endswith('e') and n2[:-3] == n1[:-1]):
            return True
        
        # 常见的双写辅音情况
        consonant_doubles = ['run', 'sit', 'begin', 'swim', 'stop']
        for base in consonant_doubles:
            gerund = base + base[-1] + 'ing'  # 如 running, sitting
            if (n1 == base and n2 == gerund) or (n1 == gerund and n2 == base):
                return True
        
        return False

    def _check_naming_convention_relation(self, name1, name2):
        """检查两个名称是否使用不同命名约定但表示相同概念
        
        处理以下命名约定差异:
        - 下划线分隔: linux_kernel
        - 连字符分隔: linux-kernel
        - 驼峰命名: LinuxKernel
        - 小驼峰命名: linuxKernel
        - 空格分隔: linux kernel
        
        Args:
            name1, name2: 要比较的两个名称
                
        Returns:
            bool: 如果两个名称仅在命名约定上不同但表示相同概念，返回True
        """
        # 规范化：将所有分隔符转为空格，同时处理驼峰
        def normalize(name):
            # 驼峰转换: AbcDef -> Abc Def
            s1 = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
            # 替换所有连词符和下划线为空格
            s2 = re.sub(r'[-_]', ' ', s1)
            # 转小写并分割
            return [word.lower() for word in s2.split() if word]
        
        # 获取词汇集合
        words1 = normalize(name1)
        words2 = normalize(name2)
        
        # 如果词汇完全相同，则属于不同命名约定的同一实体
        if words1 == words2 and words1:  # 确保不是空列表
            return True
        
        return False

    def _start_persistence_timer(self):
        """启动定期持久化任务"""
        import threading
        import time
        
        def persistence_task():
            while True:
                time.sleep(self.persistence_interval)
                self._persist_entities()
                
        persistence_thread = threading.Thread(target=persistence_task, daemon=True)
        persistence_thread.start()
        
    def _persist_entities(self):
        """将融合实体持久化到JSON文件"""
        import os
        import json
        import time
        import threading
        
        current_time = time.time()
        if current_time - self.last_persistence_time < self.persistence_interval:
            return
            
        self.logger.info("正在将融合实体持久化到JSON文件...")
        
        # 使用线程锁保护数据一致性
        lock = threading.Lock()
        
        try:
            # 确保目录存在
            os.makedirs(self.persistence_path, exist_ok=True)
            
            with lock:
                for class_name, entities in self.fused_entities_by_class.items():
                    if not entities:
                        self.logger.info(f"跳过空的实体类别: {class_name}")
                        continue
                        
                    file_path = os.path.join(self.persistence_path, f"{class_name}.json")
                    temp_file_path = f"{file_path}.tmp"
                    
                    serializable_entities = [entity.to_dict() for entity in entities]
                    if serializable_entities:
                        # 实现自己的原子写入
                        with open(temp_file_path, 'w', encoding='utf-8') as f:
                            json.dump(serializable_entities, f, indent=2, ensure_ascii=False)
                        
                        # 验证临时文件是否成功写入
                        if os.path.exists(temp_file_path) and os.path.getsize(temp_file_path) > 0:
                            # 使用os.replace进行原子替换
                            os.replace(temp_file_path, file_path)
                            self.logger.info(f"已成功持久化 {len(serializable_entities)} 个 {class_name} 类实体")
                        else:
                            self.logger.error(f"临时文件 {temp_file_path} 写入失败")
                    else:
                        self.logger.warning(f"{class_name} 类实体序列化后为空，跳过持久化")
            
            self.last_persistence_time = current_time
            self.logger.info("融合实体持久化完成")
        except Exception as e:
            self.logger.error(f"持久化融合实体时发生错误: {str(e)}")
            # 记录详细错误信息和堆栈跟踪
            import traceback
            self.logger.error(traceback.format_exc())
            
    def _load_persisted_entities(self):
        """从JSON文件加载持久化的融合实体"""
        import os
        import json
        
        self.logger.info("尝试从JSON文件加载融合实体...")
        
        try:
            # 检查目录是否存在
            if not os.path.exists(self.persistence_path):
                self.logger.info(f"持久化目录 {self.persistence_path} 不存在，跳过加载")
                return
            
            res = {}
            # 加载每个实体类别的文件
            total_entities = 0
            for class_name in Entity.ENTITY_TYPES:
                file_path = os.path.join(self.persistence_path, f"{class_name}.json")
                
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        entity_dicts = json.load(f)
                        
                    # 将字典转回实体对象
                    entities = []
                    for entity_dict in entity_dicts:
                        entity = Entity.from_dict(entity_dict)
                        entities.append(entity)

                    res[class_name] = entities
                    total_entities += len(entities)
                    self.logger.info(f"从文件加载了 {len(entities)} 个 {class_name} 类实体")
                else:
                    self.logger.info(f"未找到 {class_name} 类实体的持久化文件")
                    
            self.logger.info(f"融合实体加载完成，共 {total_entities} 个实体")
            return res
        except Exception as e:
            self.logger.error(f"加载融合实体时发生错误: {str(e)}")
            
    async def _perform_llm_based_fusion(self, rule_fused_groups: List[Entity]) -> List[Entity]:
        """对规则融合返回的实体组中，名称相同的实体使用LLM结合feature描述进行二次融合。
        这个方法不修改 self.fused_entities_by_class，它仅处理传入的列表。
        """
        if not rule_fused_groups:
            self.logger.info("LLM融合步骤：输入列表为空，直接返回。")
            return []

        final_llm_fused_entities = []
        # 创建一个副本进行操作，避免修改原始传入列表的结构（尽管内容会被修改）
        entities_to_process = [e.clone() for e in rule_fused_groups] # 假设 Entity 有 clone 方法
        processed_indices = set()
        
        for i in range(len(entities_to_process)):
            if i in processed_indices:
                continue
            
            entity1 = entities_to_process[i]
            # 不需要将i立即加入processed_indices，因为entity1本身总是要加入final_llm_fused_entities
            
            for j in range(i + 1, len(entities_to_process)):
                if j in processed_indices:
                    continue
                    
                entity2 = entities_to_process[j]
                
                if entity1.id == entity2.id: # 确保不会比较自身（虽然理论上rule_fused_groups不应有重复ID）
                    continue

                if entity1.name == entity2.name:
                    self.logger.debug(f"LLM候选: \'{entity1.name}\' (ID: {entity1.id}, Feature: {getattr(entity1, 'context', 'N/A')}) vs (ID: {entity2.id}, Feature: {getattr(entity2, 'context', 'N/A')})")
                    # 检查两个实体的context是否有一个为空或者'None'字符串
                    context1 = getattr(entity1, 'context', '')
                    context2 = getattr(entity2, 'context', '')
                    
                    if not context1 or context1 == 'None' or not context2 or context2 == 'None':
                        self.logger.info(f"实体 \'{entity1.name}\' (ID: {entity1.id}) 与 (name: {entity2.name}) 的context至少一个为空或'None'，认为是同一实体。进行合并。")
                        entity1.merge_with(entity2)  # entity2 合并到 entity1
                        processed_indices.add(j)  # entity2 已被合并，标记以便跳过
                        continue  # 跳过LLM判断，直接处理下一个实体
                    feature1_desc = getattr(entity1, 'context', 'No feature description available')
                    feature2_desc = getattr(entity2, 'context', 'No feature description available')
                    
                    prompt = f"""Identity Check: Linux Kernel Entities
Name: '{entity1.name}'

Entity 1:
  ID: {entity1.id}
  Feature: {feature1_desc}

Entity 2:
  ID: {entity2.id}
  Feature: {feature2_desc}

Do these entities refer to the same concept? Respond with 'Yes' or 'No' only."""
                    
                    try:
                        # 假设 self._get_llm_response 是同步的
                        response = self._get_llm_response(prompt)
                        self.logger.debug(f"LLM 对 \'{entity1.id}\' (IDs: {entity1.name} vs {entity2.name}) 的响应: '{response}'")
                        
                        if response and response.strip().lower() == 'yes':
                            self.logger.info(f"LLM确认 \'{entity1.id}\' (IDs: {entity1.name} vs {entity2.name}) 为同一实体。进行合并。")
                            entity1.merge_with(entity2) # entity2 合并到 entity1
                            processed_indices.add(j) # entity2 已被合并，标记以便跳过
                        else:
                            self.logger.debug(f"LLM判断 \'{entity1.id}\' (IDs: {entity1.name} vs {entity2.name}) 不是同一实体或无法判断。")
                            
                    except Exception as e:
                        self.logger.error(f"LLM调用或解析过程中发生错误 (实体IDs: {entity1.id}, {entity2.id}): {e}")
                        # 此处选择跳过此对实体的LLM判断，继续处理其他实体
                        
            final_llm_fused_entities.append(entity1) # 将 entity1 (可能已合并其他实体) 加入最终列表
            processed_indices.add(i) # 确保 entity1 本身也被标记为处理过
            
        self.logger.info(f"LLM融合处理完成。输入 {len(rule_fused_groups)} 个规则融合实体，输出 {len(final_llm_fused_entities)} 个实体。")
        return final_llm_fused_entities

    # async def _find_entity_references(self, entities):
    #     entities_with_refs = {}
    #     entities_without_refs = {}

    #     for entity in entities:
    #         entity_name = entity.name
    #         entity_key = self._create_entity_key(
    #             entity,
    #             entity.feature_id,
    #             entity.commit_ids
    #         )

    #         # 引用源验证
    #         reference = await self._find_entity_reference(
    #             entity,
    #             entity.feature_id,
    #             entity.commit_ids,
    #         )
            # entity.external_links = reference
        
    def _create_variation_prompt(self, mention: str, context: str) -> str:
        """创建生成变体的提示"""
        return f"""You are an expert in Linux kernel code. Generate ONLY the most likely Linux kernel identifier variations that would actually appear in real kernel source code.

Concept: "{mention}"
Context: "{context}"

Requirements:
- Generate MAXIMUM 5 variations
- Only include identifiers you are HIGHLY CONFIDENT exist in Linux kernel code
- Focus on the most common naming patterns:
  * Functions: lowercase_with_underscores
  * Macros/Constants: UPPERCASE_WITH_UNDERSCORES  
  * Short abbreviations commonly used in kernel

Return ONLY a JSON array of the most probable variations.

Examples:
Input: "Virtual Memory"
Output: ["vm", "vma", "virtual_memory", "VM"]

Input: "Page Table Entry"
Output: ["pte", "PTE", "page_table_entry"]

Input: "Memory Management" 
Output: ["mm", "MM", "memory_management"]

Generate for: "{mention}"
"""


    def _parse_variations_response(self, response: str, mention: str) -> List[str]:
        """解析 LLM 响应"""
        try:
            cleaned_response = strip_json(response)
            variations = json.loads(cleaned_response)
            
            if isinstance(variations, list):
                # 使用集合去重，然后转回列表，保持顺序
                unique_variations = []
                seen = set()
                for v in variations:
                    if v and isinstance(v, str):
                        v_stripped = v.strip()
                        if v_stripped and v_stripped not in seen:
                            seen.add(v_stripped)
                            unique_variations.append(v_stripped)
                return unique_variations
            return []
        except Exception as e:
            self.logger.error(f"Failed to parse variations response: {e}")
            return [mention]