# Wikipedia API 优化测试指南

本指南将帮助你验证优化后的Wikipedia API实体链接系统是否解决了429错误问题。

## 快速开始

### 1. 运行快速测试

最简单的验证方法是运行快速测试脚本：

```bash
cd /path/to/LinuxKernelKG
python scripts/quick_test_wikipedia.py
```

这个测试会：
- 使用保守的限流设置（12请求/分钟）
- 测试2个简单的实体链接
- 显示详细的API统计信息
- 给出明确的测试结果和建议

**预期结果：**
- 测试应该完成且无429错误
- 每个请求间隔应该至少3秒
- API统计中限流次数应该为0或很少

### 2. 运行完整测试

如果快速测试通过，可以运行更全面的测试：

```bash
python tests/test_wikipedia_rate_limiting.py
```

这个测试包括：
- 限流器功能测试
- 保守设置下的实体链接测试
- 错误恢复和重试机制测试
- 性能压力测试

## 测试内容详解

### 测试1: 限流器功能测试
验证RateLimiter类是否正确限制请求频率：
- 快速发送6个请求
- 验证是否有适当的等待时间
- 检查平均请求间隔

**通过标准：** 请求间隔明显增加，不会连续发送请求

### 测试2: 保守设置测试
使用非常保守的API设置测试实体链接：
- 10请求/分钟，4秒最小间隔
- 测试3个实体的链接
- 监控所有API调用

**通过标准：** 无429错误，所有请求成功处理

### 测试3: 错误恢复测试
测试在相对激进的设置下的恢复能力：
- 30请求/分钟设置
- 处理8个实体
- 验证重试机制是否生效

**通过标准：** 即使触发限流也能自动恢复

## 手动验证步骤

### 1. 检查日志文件

测试运行后，检查日志文件：

```bash
# 查看实体链接器日志
tail -f logs/entity_linker.log

# 查找429错误
grep "429" logs/entity_linker.log

# 查找限流事件
grep "Rate limited" logs/entity_linker.log
```

### 2. 监控API统计

在测试过程中，注意以下统计信息：
- `total_requests`: 总请求数
- `failed_requests`: 失败请求数
- `rate_limited_requests`: 限流次数
- `avg_requests_per_minute`: 平均请求频率

### 3. 验证请求间隔

观察测试输出中的时间戳，确认：
- 请求之间有合理的间隔
- 触发限流时等待时间增加
- 没有连续的快速请求

## 常见问题排查

### 问题1: 仍然出现429错误

**可能原因：**
- 限流设置仍然过于激进
- 网络环境有特殊限制
- Wikipedia服务器仍在限制你的IP

**解决方案：**
1. 进一步降低请求频率：
```python
config.WIKIPEDIA_RATE_LIMIT = {
    'max_requests_per_minute': 8,   # 更保守
    'max_requests_per_hour': 480,
    'min_request_interval': 5.0,    # 更长间隔
}
```

2. 增加重试延迟：
```python
config.WIKIPEDIA_RATE_LIMIT = {
    'retry_base_delay': 10.0,       # 更长的基础延迟
    'retry_max_delay': 300.0        # 更长的最大延迟
}
```

### 问题2: 测试运行很慢

**这是正常现象！** 优化的目标就是避免429错误，所以会：
- 增加请求间隔
- 实施更保守的限流
- 在出现问题时等待更长时间

**调优建议：**
- 在确认系统稳定后，可以逐步提高请求频率
- 监控API统计，确保限流次数保持在低水平

### 问题3: 测试失败但没有429错误

**可能原因：**
- 网络连接问题
- Wikipedia API临时不可用
- 实体名称或上下文问题

**排查步骤：**
1. 检查网络连接：
```bash
curl -I https://en.wikipedia.org/api/rest_v1/
```

2. 手动测试Wikipedia API：
```bash
curl "https://en.wikipedia.org/api/rest_v1/page/summary/Linux"
```

3. 检查User-Agent设置是否正确

## 生产环境建议

### 推荐配置

基于测试结果，推荐的生产环境配置：

```python
# 保守但可用的配置
WIKIPEDIA_RATE_LIMIT = {
    'max_requests_per_minute': 15,  # 每分钟15次
    'max_requests_per_hour': 900,   # 每小时900次
    'min_request_interval': 2.5,    # 2.5秒间隔
    'retry_max_attempts': 5,        # 5次重试
    'retry_base_delay': 3.0,        # 3秒基础延迟
    'retry_max_delay': 180.0        # 3分钟最大延迟
}
```

### 监控建议

1. **设置API统计监控：**
```python
# 每100个请求记录一次统计
if self.api_stats['total_requests'] % 100 == 0:
    self.log_api_stats()
```

2. **设置告警阈值：**
- 限流次数 > 5% 总请求数时告警
- 失败率 > 10% 时告警
- 平均请求频率接近上限时告警

3. **定期调整配置：**
- 根据实际使用情况优化参数
- 在系统稳定运行一段时间后，可以适当提高请求频率

## 测试结果判断

### 测试通过的标准
- ✅ 无429错误
- ✅ 限流机制正常工作
- ✅ 重试机制能够处理临时错误
- ✅ API统计信息正常

### 可以上线的条件
- 快速测试100%通过
- 完整测试至少90%通过
- 连续运行30分钟无429错误
- API统计显示请求频率在安全范围内

## 联系和支持

如果测试遇到问题：
1. 检查日志文件中的详细错误信息
2. 尝试更保守的配置设置
3. 确认网络环境和Wikipedia API可访问性
4. 考虑在不同时间段测试（避开Wikipedia流量高峰） 