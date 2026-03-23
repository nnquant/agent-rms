# agent-rms 使用指南（独立版）

## 1. 安装

### 方式 A：从本仓库本地安装（推荐）
```bash
cd /home/jiangda/develop/rms3
uv pip install ./agent-rms
```

### 方式 B：开发模式安装
```bash
cd /home/jiangda/develop/rms3
uv pip install -e ./agent-rms
```

安装后可直接使用命令：
```bash
# 若已激活当前项目虚拟环境
agent-rms --help

# 若未激活虚拟环境（推荐）
uv run agent-rms --help
```

## 2. 默认地址与环境变量

默认后端地址：
- 业务后端：`http://103.47.83.123:8060`
- 行情后端：`http://103.47.83.123:8061`

可通过环境变量覆盖：
```bash
export AGENT_RMS_API_BASE_URL=http://<backend-host>:8060
export AGENT_RMS_MARKET_API_BASE_URL=http://<market-host>:8061
```

凭证文件默认路径：
- `~/.rms3/credentials.json`

可通过环境变量覆盖：
```bash
export AGENT_RMS_CREDENTIALS_FILE=/path/to/credentials.json
```

## 3. 登录与凭证管理（auth）

### 登录
```bash
agent-rms auth login \
  --username trader1 \
  --password '******' \
  --api-base-url http://103.47.83.123:8060 \
  --market-api-base-url http://103.47.83.123:8061
```

登录成功后会写入本地凭证（不保存明文密码，文件权限自动收敛到 `0600`）。

### 查看状态
```bash
agent-rms auth status
agent-rms auth whoami
```

### 退出（删除当前 profile 凭证）
```bash
agent-rms auth logout
```

## 4. 市场数据（market）

默认输出为终端友好的表格，支持 `--output json`。

```bash
agent-rms market all
agent-rms market future
agent-rms market swap
agent-rms market future_curve
agent-rms market swap_curve
agent-rms market asw_curve
```

JSON 输出示例：
```bash
agent-rms market asw_curve --output json
```

## 5. 历史数据（history）

### 期货历史（future_curve）
```bash
agent-rms history \
  --type future_curve \
  --symbol T \
  --start-time 2026-03-01T00:00:00Z \
  --end-time 2026-03-10T00:00:00Z
```

### 互换曲线历史（swap_curve）
```bash
agent-rms history \
  --type swap_curve \
  --curve FR007 \
  --quote-type mid \
  --start-date 2026-03-01 \
  --end-date 2026-03-10
```

## 6. 组合数据（portfolio）

`overview` 默认返回当前账号可访问的全部组合，不需要 `--name`。
`detail/exposure/performance` 仍使用 `--name`（支持产品代码和产品名称，优先产品代码精确匹配）。

```bash
agent-rms portfolio overview
agent-rms portfolio detail --name P001
agent-rms portfolio exposure --name P001
agent-rms portfolio performance --name P001 --start-date 2026-01-01 --end-date 2026-03-10
```

`detail` 输出包含两张表：
- 持仓明细（`holdings_detail`）
- 策略表现（`strategy_performance`，含周/月/季/年盈亏与 DV01）

JSON 输出：
```bash
agent-rms portfolio performance --name P001 --output json
```

## 7. 输出规则

- 默认：`--output table`
- 可选：`--output json`

表格自动格式化规则：
- 金额类：千分位 + 2 位小数
- 利率/收益率/比率/价差：4 位小数
- 数量类：整数展示

## 8. AI Agent 推荐调用方式

1. 首次执行 `agent-rms auth login` 建立凭证。
2. 调试阶段先用表格（默认）观察字段。
3. 机器消费时统一加 `--output json`，解析 `data` 字段。
4. 若返回认证错误，重新执行 `agent-rms auth login`。

## 9. 常见问题

### 1) 未找到 profile 凭证
报错示例：
- `未找到 profile=default 的登录凭证`

处理：
```bash
agent-rms auth login ...
```

### 2) Token 过期
报错示例：
- `Invalid or expired token`

处理：
```bash
agent-rms auth login ...
```

### 3) 组合名歧义
报错示例：
- `组合名称存在歧义，请使用产品代码`

处理：
- 改用产品代码，例如 `--name P001`。
