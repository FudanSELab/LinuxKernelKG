import bz2
import xml.etree.ElementTree as ET
import sqlite3
import requests
import os
from tqdm import tqdm
import mwparserfromhell
import wikitextparser as wtp

class WikiDatabaseBuilder:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.chunk_size = 1000  # 每次处理的页面数
        
    def download_dump(self, dump_url: str, save_path: str):
        """下载维基百科数据转储文件"""
        if os.path.exists(save_path):
            print(f"Dump file already exists at {save_path}")
            return
            
        print(f"Downloading Wikipedia dump from {dump_url}")
        response = requests.get(dump_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        with open(save_path, 'wb') as f:
            with tqdm(total=total_size, unit='iB', unit_scale=True) as pbar:
                for data in response.iter_content(chunk_size=8192):
                    f.write(data)
                    pbar.update(len(data))
    
    def init_database(self):
        """初始化数据库结构"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # 创建页面表
        c.execute('''
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT,
            summary TEXT,
            url TEXT,
            is_disambiguation BOOLEAN,
            UNIQUE(title)
        )''')
        
        # 创建分类表
        c.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        )''')
        
        # 创建页面分类关联表
        c.execute('''
        CREATE TABLE IF NOT EXISTS page_categories (
            page_id INTEGER,
            category_id INTEGER,
            FOREIGN KEY (page_id) REFERENCES pages (id),
            FOREIGN KEY (category_id) REFERENCES categories (id),
            UNIQUE(page_id, category_id)
        )''')
        
        # 创建索引
        c.execute('CREATE INDEX IF NOT EXISTS idx_pages_title ON pages(title)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_categories_name ON categories(name)')
        
        conn.commit()
        conn.close()
    
    def process_dump(self, dump_path: str):
        """处理维基百科转储文件并导入数据库"""
        print(f"Processing Wikipedia dump file: {dump_path}")
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # 使用bz2打开压缩文件
        with bz2.open(dump_path, 'rt', encoding='utf-8') as f:
            buffer = []
            current_page = {}
            in_page = False
            
            for line in tqdm(f):
                if '<page>' in line:
                    in_page = True
                    current_page = {'categories': set()}
                elif '</page>' in line and in_page:
                    in_page = False
                    buffer.append(current_page)
                    
                    if len(buffer) >= self.chunk_size:
                        self._process_buffer(c, buffer)
                        buffer = []
                        conn.commit()
                
                elif in_page:
                    if '<title>' in line:
                        current_page['title'] = line.strip().replace('<title>', '').replace('</title>', '')
                    elif '<text' in line:
                        content = line.split('>', 1)[1].rsplit('</', 1)[0]
                        current_page['content'] = content
                        
                        # 解析维基文本
                        parsed = wtp.parse(content)
                        
                        # 提取分类
                        for category in parsed.wikilinks:
                            if category.title.startswith('Category:'):
                                current_page['categories'].add(category.title[9:])
                        
                        # 检查是否为消歧义页面
                        current_page['is_disambiguation'] = (
                            '{{disambiguation}}' in content.lower() or
                            '{{disambig}}' in content.lower()
                        )
            
            # 处理剩余的页面
            if buffer:
                self._process_buffer(c, buffer)
                conn.commit()
        
        conn.close()
        print("Database creation completed")
    
    def _process_buffer(self, cursor, buffer):
        """处理一批页面数据"""
        for page in buffer:
            # 插入页面
            cursor.execute('''
            INSERT OR IGNORE INTO pages (title, content, is_disambiguation, url)
            VALUES (?, ?, ?, ?)
            ''', (
                page['title'],
                page['content'],
                page['is_disambiguation'],
                f"https://en.wikipedia.org/wiki/{page['title'].replace(' ', '_')}"
            ))
            
            page_id = cursor.lastrowid
            
            # 处理分类
            for category in page['categories']:
                # 插入分类
                cursor.execute('INSERT OR IGNORE INTO categories (name) VALUES (?)', (category,))
                cursor.execute('SELECT id FROM categories WHERE name = ?', (category,))
                category_id = cursor.fetchone()[0]
                
                # 关联页面和分类
                cursor.execute('''
                INSERT OR IGNORE INTO page_categories (page_id, category_id)
                VALUES (?, ?)
                ''', (page_id, category_id))

def main():
    # 配置参数
    DB_PATH = 'data/wikipedia.db'
    DUMP_PATH = 'data/enwiki-latest-pages-articles.xml.bz2'
    DUMP_URL = 'https://dumps.wikimedia.org/enwiki/latest/enwiki-latest-pages-articles.xml.bz2'
    
    # 创建构建器实例
    builder = WikiDatabaseBuilder(DB_PATH)
    
    # 下载数据转储文件
    builder.download_dump(DUMP_URL, DUMP_PATH)
    
    # 初始化数据库
    builder.init_database()
    
    # 处理数据转储文件
    builder.process_dump(DUMP_PATH)

if __name__ == '__main__':
    main() 