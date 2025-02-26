import asyncio
import wikipediaapi
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import aiohttp
import logging
from typing import List, Dict, Optional

class MultiSourceSearcher:
    def __init__(self):
        # 设置日志
        self.logger = logging.getLogger('multi_source_searcher')
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(handler)
        
        # 初始化Wikipedia API
        self.wiki = wikipediaapi.Wikipedia(
            language='en',
            extract_format=wikipediaapi.ExtractFormat.HTML,
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )

    def search_all(self,feature_description, term: str) -> Dict:
        """执行所有来源的搜索
        
        Args:
            term: 要搜索的术语
            
        Returns:
            Dict: 包含所有搜索结果的字典
        """
    
        self.logger.info(f"===================开始搜索术语: {term}==================")
        
        # 并行执行所有搜索
        wiki_result = self._search_wikipedia_online(term)
        if wiki_result is None:
            bootlin_result = self._search_bootlin(term)
            kernel_docs_result = self._search_kernel_docs(term)
        else:
            bootlin_result = None
            kernel_docs_result = None   
        
        # 整合所有结果
        results = {
            'term': term,
            'feature_description': feature_description,
            'wikipedia': wiki_result,
            'bootlin': bootlin_result,
            'kernel_docs': kernel_docs_result
        }
            
        
        return results

    def process_extraction_result(self, extraction_result: List[Dict]) -> List[Dict]:
        """处理提取结果并进行搜索"""
        search_results = []
        for result in extraction_result:
            entities = result.get('entities', '')
            for entity in entities:
                feature_description = result.get('feature_description', '')
                if feature_description:
                    search_result = self.search_all(feature_description, entity)
                search_results.append(search_result)
        return search_results

    def _search_wikipedia_online(self, term: str) -> Optional[Dict]:
        """搜索维基百科"""
        try:
            page = self.wiki.page(term)
            
            if not page.exists():
                return None
                
            return {
                'title': page.title,
                'url': page.fullurl,
                'summary': page.summary[:200],
                'exists': True
            }
            
        except Exception as e:
            self.logger.error(f"Wikipedia search failed for term {term}: {e}")
            return None

    def _search_bootlin(self, term: str) -> Optional[Dict]:
        """搜索Bootlin"""
        if term.endswith('()'):
            term = term[:-2]

        base_url = 'https://elixir.bootlin.com/linux/v6.12.6/A/ident/'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        url = f"{base_url}{term}"
        try:
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                self.logger.info(f'在 Bootlin 找到与 "{term}" 相关的结果')
                return {
                    'url': url,
                    'title': f"Bootlin search result for {term}",
                    'exists': True
                }
            
            underscored_term = '_'.join(term.split())
            if underscored_term != term:
                url = f"{base_url}{underscored_term}"
                response = requests.get(url, headers=headers)
                
                if response.status_code == 200:
                    self.logger.info(f'在 Bootlin 找到与 "{underscored_term}" 相关的结果')
                    return {
                        'url': url,
                        'title': f"Bootlin search result for {underscored_term}",
                        'exists': True
                    }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Bootlin search failed for term {term}: {e}")
            return None

    def _search_kernel_docs(self, term: str) -> Optional[Dict]:
        """搜索Kernel文档"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

        driver = None
        try:
            base_url = 'https://docs.kernel.org/search.html?q='
            driver = webdriver.Chrome(options=chrome_options)
            url = f"{base_url}{term}"
            driver.get(url)

            wait = WebDriverWait(driver, 6)
            search_summary = wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, "search-summary"))
            ).text

            if "did not match any documents" in search_summary:
                return None

            references = []
            try:
                search_container = wait.until(
                    EC.presence_of_element_located((By.CLASS_NAME, "search"))
                )
                links = search_container.find_elements(By.TAG_NAME, "a")
                
                for link in links[:5]:
                    result_url = link.get_attribute('href')
                    if result_url and result_url.startswith('http'):
                        references.append({
                            'url': result_url,
                            'title': link.text
                        })
                
                if references:
                    return {
                        'references': references,
                        'exists': True
                    }
                    
            except Exception as e:
                self.logger.warning(f"Error processing kernel docs links: {e}")
                return None

        except Exception as e:
            self.logger.error(f"Kernel docs search failed for term {term}: {e}")
            return None
            
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
                    
        return None

def main():
    # 使用示例
    searcher = MultiSourceSearcher()
    terms = ["Drivers",
"Drivers & architectures",
"Drivers & Architecture",
"Networking",
"Filesystems",
"Kernel Core changes",
"Architecture-specific",
"Various core changes",
"SELinux/audit",
"i2c",
"acpiphp",
"hwmon",
"pcmcia",
"Serial:",
"dm/md:",
"LED",
"Various stuff:",
"mmc",
"Drivers and other subsystems",
"Important things (AKA: ''the cool stuff'')",
"Architecture-specific changes",
"SELinux",
"Arch-independent changes in the kernel core",
"Crypto",
"CPUFREQ",
"Various subsystems",
"Subsystems",
"Important features (AKA: the cool stuff)",
"Prominent features (the cool stuff)",
"Core",
"Security",
"Various core",
"Tracing/Profiling",
"Block",
"WIFI",
"Wi-Fi",
"Tracing",
"DM/MD",
"Virtualization",
"PCI",
"Ftrace",
"DM",
"Memory management",
"MD/DM",
"Cgroups",
"MD",
"CPU scheduler",
"Cpufreq/cpuidle",
"VFS scalability work",
"Tracing/perf",
"Prominent features",
"VFS",
"Process scheduler",
"Prominent features in the 3.1 kernel",
"Block layer",
"Prominent features in Linux 3.2",
"Device Mapper",
"Power management",
"Prominent features in Linux 3.3",
"Prominent features in Linux 3.4",
"Perf profiling",
"Prominent features in Linux 3.5",
"Perf/tracing",
"Prominent features in Linux 3.6",
"Cryptography",
"Prominent features in Linux 3.7",
"Perf",
"Prominent features in Linux 3.8",
"Crypto/keyring",
"Prominent features in Linux 3.9",
"Tracing & perf",
"Core (various)",
"List of merges",
"Tracing and perf tool",
"Architectures",
"Tracing, perf, BPF",
"Graphics",
"Tracing, perf and BPF",
"Coolest features",
"Tracing and perf",
"List of feature merges",
"Block Devices",
"BPF",
"Tracing, perf",
"Tracing, probing and BPF"]  # 将此处替换为你想要的术语列表
    
    for term in terms:
        results = searcher.search_all(term)
        
        with open("search_results.txt", "a", encoding="utf-8") as file:
            file.write("\n=== 搜索结果 ===\n")
            file.write(f"搜索术语: {results['term']}\n")
            
            # Wikipedia结果
            file.write("\n--- Wikipedia ---\n")
            if results['wikipedia']:
                file.write(f"标题: {results['wikipedia']['title']}\n")
                file.write(f"URL: {results['wikipedia']['url']}\n")
                file.write(f"摘要: {results['wikipedia']['summary']}\n")
            else:
                file.write("未找到Wikipedia结果\n")
            
            # Bootlin结果
            file.write("\n--- Bootlin ---\n")
            if results['bootlin']:
                file.write(f"URL: {results['bootlin']['url']}\n")
                file.write(f"标题: {results['bootlin']['title']}\n")
            else:
                file.write("未找到Bootlin结果\n")
            
            # Kernel Docs结果
            file.write("\n--- Kernel Docs ---\n")
            if results['kernel_docs']:
                file.write("找到以下参考文档:\n")
                for ref in results['kernel_docs']['references']:
                    file.write(f"- {ref['title']}\n")
                    file.write(f"  {ref['url']}\n")
            else:
                file.write("未找到Kernel Docs结果\n")

if __name__ == "__main__":
    main() 