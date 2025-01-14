import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import logging
from selenium.common.exceptions import TimeoutException, WebDriverException
import sys
import pandas as pd
import json
import os

# 设置日志级别
logging.getLogger('selenium').setLevel(logging.ERROR)

# 设置请求头，防止被反爬虫机制拒绝
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36'
}

# 添加输出缓冲区刷新
def print_and_flush(*args, **kwargs):
    print(*args, **kwargs)
    sys.stdout.flush()

def load_search_terms():
    """从Excel文件加载搜索词和ID"""
    df = pd.read_excel('data/entity_fusion_benchmark_0108.xlsx')
    search_terms = []
    for _, row in df.iterrows():
        # 如果commit_ids是字符串形式，将其转换为列表
        commit_ids = row['commit_ids']
        if isinstance(commit_ids, str):
            try:
                commit_ids = json.loads(commit_ids.replace("'", '"'))
            except:
                commit_ids = []
        elif pd.isna(commit_ids):
            commit_ids = []
            
        term = {
            'original_mention': row['original_mention'],
            'feature_id': row['feature_id'],
            'commit_ids': commit_ids  # 现在直接存储为列表
        }
        search_terms.append(term)
    return search_terms

def _get_cache_key(entity: str, feature_id: str, commit_ids: list) -> str:
    """统一的缓存键生成方法"""
    # 确保 commit_ids 是列表
    if commit_ids is None:
        commit_ids = []
    elif not isinstance(commit_ids, list):
        commit_ids = [commit_ids]
    
    # 确保所有元素都是字符串，过滤掉空值，并排序
    commit_ids = sorted([str(cid) for cid in commit_ids if cid])
    
    # 用下划线连接所有commit_ids
    commit_ids_str = '_'.join(commit_ids)
    
    feature_id_str = feature_id if feature_id else ''
    return f"{entity}_{feature_id_str}_{commit_ids_str}"

def load_cache():
    """加载缓存文件"""
    cache_file = 'data/cache/fusion_cache.json'
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_cache(cache_data):
    """保存缓存文件"""
    cache_file = 'data/cache/fusion_cache.json'
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2)

def search_identifier_bootlin(base_url, term):
    """搜索Bootlin并返回结构化结果"""
    identifier = term['original_mention']
    # 去除标识符末尾的括号
    if identifier.endswith('()'):
        identifier = identifier[:-2]
    url = f"{base_url}{identifier}"
    
    response = requests.get(url, headers=headers)
    
    result = {
        "entity": identifier,
        "references": [],
        "found": False
    }
    
    if response.status_code == 200:
        print_and_flush(f'在 Bootlin 找到与 "{identifier}" 相关的结果。')
        result["found"] = True
        result["reference_type"]= "code",
        result["reference_source"]= "bootlin",  
        result["references"].append({
            "entity": identifier,
            "references": [{
                "url": url,
                "title": f"Bootlin search result for {identifier}"
            }]
        })
    else:
        print_and_flush(f'Bootlin 请求失败，状态码: {response.status_code}')
    return result

def search_identifier_kernel_docs(base_url, identifier):
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--silent')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    chrome_options = Options()
    driver = None
    try:
        print_and_flush(f"\n开始搜索 {identifier}...")
        driver = webdriver.Chrome(options=chrome_options)
        url = f"{base_url}{identifier}"
        driver.get(url)

        # 设置较短的等待时间
        wait = WebDriverWait(driver, 5)

        try:
            # 只等待 search-summary 元素
            search_summary = wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, "search-summary"))
            ).text

            if search_summary.startswith("Your search did not match any documents."):
                print_and_flush(f'在 Kernel Docs 没有找到与 "{identifier}" 相关的结果。')
                return (identifier, None)

            found_results = []
            links = driver.find_elements(By.TAG_NAME, "a")
            
            for link in links:
                try:
                    result_url = link.get_attribute('href')
                    if not result_url or not result_url.startswith('http'):
                        continue
                    
                    # 获取链接页面的内容
                    response = requests.get(result_url, headers=headers, timeout=5)
                    if response.status_code == 200:
                        # 使用BeautifulSoup解析页面内容
                        soup = BeautifulSoup(response.text, 'html.parser')
                        # 获取页面文本内容
                        page_text = soup.get_text().lower()
                        # 检查关键字是否在页面内容中
                        if identifier.lower() in page_text:
                            found_results.append(result_url)
                            print_and_flush(f'在 Kernel Docs 找到相关内容: {result_url}')
                except Exception as e:
                    continue

            if found_results:
                return (identifier, found_results)
            else:
                print_and_flush(f'在 Kernel Docs 没有找到与 "{identifier}" 相关的内容。')
                return (identifier, None)

        except TimeoutException:
            print_and_flush(f'在 Kernel Docs 搜索超时: "{identifier}"')
            return (identifier, None)

    except WebDriverException as e:
        print_and_flush(f"WebDriver错误: {str(e)}")
        return (identifier, None)
    except Exception as e:
        print_and_flush(f"搜索过程中发生错误: {str(e)}")
        return (identifier, None)
    
    finally:
        if driver:
            try:
                driver.close()
            except Exception:
                pass
            try:
                driver.quit()
            except Exception:
                pass

# 示例调用
base_url_bootlin = 'https://elixir.bootlin.com/linux/v6.12.6/A/ident/'
base_url_kernel_docs = 'https://docs.kernel.org/search.html?q='

# 定义搜索关键词列表
# identifiers = ['folio_orderl','folio_order']
# identifiers = [
#     'handle_pte_fault', 'mmu cache update', 'PTE_MARKER_POISONED', 'CONFIG_NUMA',
#     'NUMA PTE faults', 'destroy_large_folio()', 'in hpage_collapse_scan_file()',
#     'Static random selection', 'mmap lock hold time', 'do_cow_fault', 'THPs',
#     'per-page to per-folio', 'kunit', 'THP', 'gup test matrix', 'cacheline',
#     'VMA insertion', 'buffer', 'userfaultfd API', 'destroy_large_folio',
#     'VMA operations', 'for large folio', 'Per-page to Per-folio', 'MADV_UNMERGEABLE',
#     'Entirely', 'filemap_map_folio_range()', 'Unneeded', '__lruvec_stat for large folio',
#     'folio_add_file_rmap_range()', 'slab allocator', 'KSM-placed zeropages',
#     'If cachefiles object contains data when opened', 'truncate_inode_pages_final',
#     'critical section', 'vma_assert_write_locked()', 'bio_first_folio_all()',
#     'pgtable management', 'OSQ_Lock', 'NUMA migration handling', 'hugetlb gup requests',
#     'folio_undo_large_rmappable()', 'ops->migrate_to_ram', 'KVM', 'replace_page_tables()',
#     'page table range API', 'vma lock', 'own ioremap_prot(), ioremap() and iounmap() definitions',
#     'Architectures', 'do_shared_fault', 'accessed bit', 'page_add_file_rmap',
#     'Per-VMA locks', 'change in flag granularity', 'Nios2 architecture',
#     'follow_hugetlb_page', 'numa_cma=', 'OpenRISC architecture',
#     'collapse_pte_mapped_thp()', 'swapcache', 'specifying optional tests',
#     'cma_declare_contiguous_nid()', 'DAMON', 'lseek after HWPOISON subpage',
#     'multiple copies of generic slab caches', 'vma_start_write()', '__get_user_pages()',
#     'DMA_PERNUMA_CMA', 'PG_dcache_clean', 'DAMOS tried regions', 'CoW', 'gup_test',
#     "Operations on file's i_mmap tree", 'HUGETLB_PAGE_DTOR', 'i_mmap tree',
#     'llist_del_all', 'flush_dcache_folio()', 'pmd_ptlock_init()', 'vma locking',
#     'pgtable_pte_ctor', 'free_transhuge_folio()', 'separate cache line',
#     'descriptor', 'Minor performance overhead', 'Parisc architecture',
#     'page_add_file_rmap()', 'page flags', 'heap spraying prevention',
#     'Unsharing KSM-placed zero pages', 'gup', '__split_huge_page_tail()',
#     'Setting up N page table entries at once', 'Retrieving monitoring results snapshot',
#     'jbd2_journal_write_metadata_buffer', 'ARM architecture', 'FOLL_PIN',
#     'update_mmu_cache_range', 'FSCACHE_COOKIE_NO_DATA_TO_READ', 'free table page',
#     'mmap_write_lock()', 'pmd_t'
# ]

# # 遍历列表中的每个标识符进行搜索
# for identifier in identifiers:
#     print_and_flush(f"\n正在搜索: {identifier}")
#     search_identifier_bootlin(base_url_bootlin, identifier)
#     # search_identifier_kernel_docs(base_url_kernel_docs, identifier)
#     chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

    # 确保输出是无缓冲的
def main():
    base_url_bootlin = 'https://elixir.bootlin.com/linux/v6.12.6/A/ident/'
    base_url_kernel_docs = 'https://docs.kernel.org/search.html?q='
    
    search_terms = load_search_terms()
    cache = load_cache()
    
    for term in search_terms:
        cache_key = _get_cache_key(term['original_mention'], term['feature_id'], term['commit_ids'])
        
        # 获取新的搜索结果
        print_and_flush(f"\n正在搜索: {term['original_mention']}")
        new_result = search_identifier_bootlin(base_url_bootlin, term)
        
        if cache_key in cache:
            # 确保缓存条目有基本结构
            if 'references' not in cache[cache_key]:
                cache[cache_key]['references'] = []
            if 'entity' not in cache[cache_key]:
                cache[cache_key]['entity'] = term['original_mention']
            
            # 如果已存在缓存，合并新的搜索结果
            existing_refs = {
                (ref['reference_source'], ref['reference_type']): ref 
                for ref in cache[cache_key]['references']
            }
            
            # 添加新的引用，避免重复
            for new_ref in new_result['references']:
                key = (new_ref['reference_source'], new_ref['reference_type'])
                if key not in existing_refs:
                    cache[cache_key]['references'].append(new_ref)
                else:
                    # 合并引用列表
                    existing_urls = {ref['url'] for ref in existing_refs[key]['references']}
                    for ref in new_ref['references']:
                        if ref['url'] not in existing_urls:
                            existing_refs[key]['references'].append(ref)
                            existing_urls.add(ref['url'])
        else:
            # 如果不存在缓存，直接添加新结果
            cache[cache_key] = new_result
        
        # 定期保存缓存
        save_cache(cache)

if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()

