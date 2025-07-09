#!/usr/bin/env python3
"""
网络连接测试脚本
用于诊断Wikipedia API访问问题
"""

import requests
import time
from datetime import datetime
import urllib3
from urllib3.exceptions import InsecureRequestWarning

# 禁用SSL警告
urllib3.disable_warnings(InsecureRequestWarning)

def test_wikipedia_connectivity():
    """测试Wikipedia API连接"""
    print("=" * 60)
    print("Wikipedia API 网络连接测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 测试不同的Wikipedia端点
    test_urls = [
        "https://en.wikipedia.org",
        "https://en.wikipedia.org/api/rest_v1/",
        "https://en.wikipedia.org/w/api.php",
        "https://en.wikipedia.org/api/rest_v1/page/summary/Linux"
    ]
    
    results = []
    
    for i, url in enumerate(test_urls, 1):
        print(f"\n[{i}/{len(test_urls)}] 测试: {url}")
        
        start_time = time.time()
        try:
            # 设置较短的超时时间
            response = requests.get(
                url, 
                timeout=(5, 10),  # 连接超时5秒，读取超时10秒
                headers={
                    'User-Agent': 'LinuxKernelKG/1.0 (Educational research project; Linux kernel knowledge graph; contact: admin@example.com) Python/3.x'
                }
            )
            
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                print(f"✓ 连接成功 (状态码: {response.status_code}, 耗时: {elapsed:.2f}s)")
                results.append({'url': url, 'success': True, 'time': elapsed, 'status': response.status_code})
            else:
                print(f"⚠ 连接异常 (状态码: {response.status_code}, 耗时: {elapsed:.2f}s)")
                results.append({'url': url, 'success': False, 'time': elapsed, 'status': response.status_code})
                
        except requests.exceptions.ConnectTimeout:
            elapsed = time.time() - start_time
            print(f"✗ 连接超时 (耗时: {elapsed:.2f}s)")
            results.append({'url': url, 'success': False, 'time': elapsed, 'error': 'ConnectTimeout'})
            
        except requests.exceptions.ReadTimeout:
            elapsed = time.time() - start_time
            print(f"✗ 读取超时 (耗时: {elapsed:.2f}s)")
            results.append({'url': url, 'success': False, 'time': elapsed, 'error': 'ReadTimeout'})
            
        except requests.exceptions.ConnectionError as e:
            elapsed = time.time() - start_time
            print(f"✗ 连接错误 (耗时: {elapsed:.2f}s): {str(e)[:100]}...")
            results.append({'url': url, 'success': False, 'time': elapsed, 'error': 'ConnectionError'})
            
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"✗ 未知错误 (耗时: {elapsed:.2f}s): {str(e)[:100]}...")
            results.append({'url': url, 'success': False, 'time': elapsed, 'error': str(type(e).__name__)})
    
    # 生成测试报告
    print("\n" + "=" * 60)
    print("连接测试报告")
    print("=" * 60)
    
    successful_tests = sum(1 for r in results if r['success'])
    total_tests = len(results)
    
    print(f"总测试数: {total_tests}")
    print(f"成功连接: {successful_tests}")
    print(f"失败连接: {total_tests - successful_tests}")
    print(f"成功率: {successful_tests/total_tests*100:.1f}%")
    
    if successful_tests == 0:
        print("\n❌ 所有连接都失败了！")
        print("\n可能的解决方案:")
        print("1. 检查网络连接是否正常")
        print("2. 检查是否需要代理设置")
        print("3. 尝试以下命令启用代理:")
        print("   export HTTP_PROXY=your_proxy_url")
        print("   export HTTPS_PROXY=your_proxy_url")
        print("4. 检查防火墙设置")
        print("5. 尝试使用VPN")
        
    elif successful_tests < total_tests:
        print(f"\n⚠ 部分连接成功 ({successful_tests}/{total_tests})")
        print("Wikipedia API可能可以使用，但连接不稳定")
        print("建议:")
        print("- 增加重试次数和延迟时间")
        print("- 使用更保守的超时设置")
        
    else:
        print("\n✅ 所有连接都成功！")
        print("Wikipedia API访问正常，可以进行实体链接测试")
    
    # 建议的配置
    print(f"\n推荐的超时配置:")
    avg_time = sum(r['time'] for r in results if r['success']) / max(successful_tests, 1)
    recommended_timeout = max(int(avg_time * 3), 10)
    
    print(f"基于测试结果，建议设置:")
    print(f"- 连接超时: {recommended_timeout}秒")
    print(f"- 读取超时: {recommended_timeout * 2}秒")
    print(f"- 重试次数: 5次")
    print(f"- 重试基础延迟: {max(int(avg_time), 5)}秒")

if __name__ == "__main__":
    test_wikipedia_connectivity() 