# agent-rms 使用指南（独立版）

## 1. 安装

推荐流程：先 `git clone`，再将项目安装为 `uv tool`。

### 方式 A：clone 后安装为 uv tool（推荐）
```bash
git clone <repo-url>
cd agent-rms
uv tool install .
```

安装完成后，推荐通过 `uvx` 调用：
```bash
uvx agent-rms --help
```

说明：
- `uv tool install .` 会把当前项目作为工具安装到独立环境中。
- `uvx agent-rms ...` 是 `uv tool run` 的简写；若工具已安装，会优先复用已安装版本。
- 如果本机 shell 已正确加入 uv 的工具目录，也可以直接执行 `agent-rms ...`，但对 Agent 来说更推荐统一使用 `uvx agent-rms ...`。

### 方式 B：直接从 Git 源安装为 uv tool
```bash
uv tool install git+<repo-url>
uvx agent-rms --help
```

### 方式 C：开发调试
```bash
git clone <repo-url>
cd agent-rms
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
uvx agent-rms auth login \
  --username trader1 \
  --password '******' \
  --api-base-url http://103.47.83.123:8060 \
  --market-api-base-url http://103.47.83.123:8061
```

登录成功后会写入本地凭证（不保存明文密码，文件权限自动收敛到 `0600`）。

### 查看状态
```bash
uvx agent-rms auth status
uvx agent-rms auth whoami
```

### 退出（删除当前 profile 凭证）
```bash
uvx agent-rms auth logout
```

## 4. 市场数据（market）

默认输出为终端友好的表格，支持 `--output json`。

```bash
uvx agent-rms market all
uvx agent-rms market future
uvx agent-rms market swap
uvx agent-rms market future_curve
uvx agent-rms market swap_curve
uvx agent-rms market asw_curve
```

补充说明：
- `future_curve`、`asw_curve`、`market all` 会优先参考 `/market/bond_futures/history` 最近主力历史来选当前主力合约，而不是简单按远月合约代码排序。

JSON 输出示例：
```bash
uvx agent-rms market asw_curve --output json
```

## 5. 历史数据（history）

`history` 返回的是曲线利差历史，而不是底层单个合约的原始历史点位。

### 期货曲线利差历史（future_curve）
```bash
uvx agent-rms history \
  --type future_curve \
  --pair TxTL \
  --start-time 2026-03-01T00:00:00Z \
  --end-time 2026-03-10T00:00:00Z
```

若不传 `--pair`，会返回全部期货利差对；可选值包括 `TSxTF`、`TSxT`、`TSxTL`、`TFxT`、`TFxTL`、`TxTL`。

### 互换曲线利差历史（swap_curve）
```bash
uvx agent-rms history \
  --type swap_curve \
  --pair 1x5 \
  --start-date 2026-03-01 \
  --end-date 2026-03-10
```

若不传 `--pair`，会返回全部互换利差对；当前支持 `1x2`、`1x5`、`2x5`。底层数据源仍通过 `--curve` 和 `--quote-type` 控制，默认是 `FR007` + `mid`。

## 6. 行情录入（quote）

`quote` 直接调用业务后端的行情录入 API，支持 AI 草稿和直提两种模式。

### 创建草稿
```bash
uvx agent-rms quote draft \
  --instrument-code IRS_5Y_PAY \
  --template irs \
  --last-price 1.9200 \
  --bid-price 1.9100 \
  --ask-price 1.9300
```

### 直接提交并生效
```bash
uvx agent-rms quote submit \
  --instrument-code BOND_240210 \
  --template bond \
  --last-yield 1.8800 \
  --cover-minutes 15
```

### 确认草稿
```bash
uvx agent-rms quote confirm --entry-id 18
```

### 查看录入记录与当前有效行情
```bash
uvx agent-rms quote list --instrument-code IRS_5Y_PAY
uvx agent-rms quote effective --instrument-code IRS_5Y_PAY
```

字段规则：
- `irs`：`--last-price` 必填，`--bid-price/--ask-price` 可选
- `bond`：`--last-yield` 必填，`--last-clean-price` 可选
- `--cover-minutes` 默认 `10`
- `--source` 默认 `agent`，也可显式传 `manual`

## 7. 组合数据（portfolio）

`overview` 默认返回当前账号可访问的全部组合，不需要 `--name`。
`detail/exposure/performance` 仍使用 `--name`（支持产品代码和产品名称，优先产品代码精确匹配）。

```bash
uvx agent-rms portfolio overview
uvx agent-rms portfolio detail --name P001
uvx agent-rms portfolio exposure --name P001
uvx agent-rms portfolio performance --name P001 --start-date 2026-01-01 --end-date 2026-03-10
```

`detail` 输出包含两张表：
- 持仓明细（`holdings_detail`）
- 策略表现（`strategy_performance`，含周/月/季/年盈亏与 DV01）

JSON 输出：
```bash
uvx agent-rms portfolio performance --name P001 --output json
```

## 8. 输出规则

- 默认：`--output table`
- 可选：`--output json`

表格自动格式化规则：
- 金额类：千分位 + 2 位小数
- 利率/收益率/比率/价差：4 位小数
- 数量类：整数展示

## 9. AI Agent 推荐调用方式

最佳实践：

1. 先执行 `git clone <repo-url>` 获取项目源码，再进入仓库目录执行 `uv tool install .`。
2. 统一使用 `uvx agent-rms ...` 调用，不依赖当前 shell 是否激活虚拟环境。
3. 首次执行 `uvx agent-rms auth login` 建立凭证。
4. 调试阶段先用表格（默认）观察字段。
5. 机器消费时统一加 `--output json`，解析 `data` 字段。
6. 若返回认证错误，重新执行 `uvx agent-rms auth login`。

补充说明：
- 若已经把 uv 工具目录加入 `PATH`，也可以直接执行 `agent-rms ...`。
- 对 Agent 来说，固定写成 `uvx agent-rms ...` 更稳妥，便于跨机器、跨 shell、跨会话复用。

## 10. 常见问题

### 1) 未找到 profile 凭证
报错示例：
- `未找到 profile=default 的登录凭证`

处理：
```bash
uvx agent-rms auth login ...
```

### 2) Token 过期
报错示例：
- `Invalid or expired token`

处理：
```bash
uvx agent-rms auth login ...
```

### 3) 组合名歧义
报错示例：
- `组合名称存在歧义，请使用产品代码`

处理：
- 改用产品代码，例如 `--name P001`。
