import requests

try:
    response = requests.get('https://www.wikipedia.org', timeout=5)  # 设置5秒超时
    print(f"状态码: {response.status_code}")
except requests.exceptions.Timeout:
    print("请求超时，请检查网络连接")
except requests.exceptions.ConnectionError:
    print("连接错误，请检查网络或URL")
except requests.exceptions.RequestException as e:
    print(f"请求发生错误: {e}")