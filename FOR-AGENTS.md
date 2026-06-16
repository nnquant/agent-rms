# FOR-AGENTS.md

本文是给自动化 Agent 使用 `agent-rms` 的操作手册，覆盖安装、配置、登录、读数据、
写行情、录入期货手工交易、错误恢复和审计记录。

## 1. 能力边界

`agent-rms` 是面向 AI Agent 的 RMS3 独立 CLI。

可以使用它做：

- 登录和本地凭证管理
- 查询最新市场数据
- 查询期货、互换、ASW 等派生曲线
- 查询历史曲线利差
- 查询组合、持仓、风险敞口和绩效
- 录入、确认和查询行情覆盖
- 创建、修改和删除期货手工交易

不要使用它做：

- 直接访问数据库
- 管理 RMS3 服务进程
- 绕过后端权限
- 修改 IRS 交易生命周期
- 在 prompt、日志或源码里保存密码和 token

后端是最终权威。CLI 只做本地输入形状校验；权限、产品范围、合约有效性、当日交易
限制和已结算保护都由 RMS3 后端强制校验。

## 2. 安装

推荐安装方式：

```bash
git clone <repo-url>
cd agent-rms
uv tool install .
uvx agent-rms --help
```

从 Git 源直接安装：

```bash
uv tool install git+<repo-url>
uvx agent-rms --help
```

开发调试方式：

```bash
git clone <repo-url>
cd agent-rms
uv run agent-rms --help
```

Agent 默认调用方式：

```bash
uvx agent-rms ...
```

优先使用 `uvx`，不要依赖当前 shell 是否激活虚拟环境。这样在远端 shell、定时任务、
子进程和多轮 Agent 会话里更稳定。

## 3. 地址和环境变量

默认后端地址：

- 业务后端：`http://103.47.83.123:8060`
- 行情后端：`http://103.47.83.123:8061`

如需覆盖：

```bash
export AGENT_RMS_API_BASE_URL=http://<backend-host>:8060
export AGENT_RMS_MARKET_API_BASE_URL=http://<market-host>:8061
```

默认凭证文件：

```bash
~/.rms3/credentials.json
```

如需隔离凭证：

```bash
export AGENT_RMS_CREDENTIALS_FILE=/tmp/agent-rms-credentials.json
```

凭证文件保存 token，不保存明文密码，权限会收敛到 `0600`。

## 4. 登录

登录：

```bash
uvx agent-rms auth login \
  --username <username> \
  --password '<password>' \
  --api-base-url http://103.47.83.123:8060 \
  --market-api-base-url http://103.47.83.123:8061
```

查看本地登录状态：

```bash
uvx agent-rms auth status --output json
```

校验 token 是否可用：

```bash
uvx agent-rms auth whoami --output json
```

退出登录：

```bash
uvx agent-rms auth logout
```

Agent 规则：如果当前任务不是自己刚完成登录，在读写数据前先执行 `auth status` 或
`auth whoami`。

## 5. 输出协议

大多数命令支持：

```bash
--output table
--output json
```

Agent 应默认使用 JSON：

```bash
uvx agent-rms market all --output json
```

成功输出结构：

```json
{
  "ok": true,
  "source": "backend or derived source",
  "request": {
    "profile": "default"
  },
  "data": {},
  "ts": "2026-06-16T01:30:00.000000Z"
}
```

解析规则：

- 先检查进程退出码
- 退出码为 `0` 时再解析 JSON
- 业务数据只从 `data` 读取
- 审计记录里保留 `source`、`request` 和 `ts`

## 6. 市场数据

最新市场数据：

```bash
uvx agent-rms market all --output json
uvx agent-rms market future --output json
uvx agent-rms market swap --output json
uvx agent-rms market future_curve --output json
uvx agent-rms market swap_curve --output json
uvx agent-rms market asw_curve --output json
```

注意：

- `future_curve`、`asw_curve`、`market all` 会参考近期主力合约历史，不是简单按远月排序。
- `market` 命令都是只读命令。
- 市场响应为空不一定代表后端挂了；先看 `source`、请求参数、交易时段和上游数据状态。

## 7. 历史数据

期货曲线利差历史：

```bash
uvx agent-rms history \
  --type future_curve \
  --pair TxTL \
  --start-time 2026-03-01T00:00:00Z \
  --end-time 2026-03-10T00:00:00Z \
  --output json
```

支持的期货利差对：

- `TSxTF`
- `TSxT`
- `TSxTL`
- `TFxT`
- `TFxTL`
- `TxTL`

互换曲线利差历史：

```bash
uvx agent-rms history \
  --type swap_curve \
  --pair 1x5 \
  --start-date 2026-03-01 \
  --end-date 2026-03-10 \
  --output json
```

支持的互换利差对：

- `1x2`
- `1x5`
- `2x5`

`history` 返回的是派生利差行，不是底层单合约 tick 或原始点位。

## 8. 组合数据

组合总览：

```bash
uvx agent-rms portfolio overview --output json
```

组合明细：

```bash
uvx agent-rms portfolio detail --name <product-code-or-name> --output json
```

风险敞口：

```bash
uvx agent-rms portfolio exposure --name <product-code-or-name> --output json
```

绩效：

```bash
uvx agent-rms portfolio performance \
  --name <product-code-or-name> \
  --start-date 2026-01-01 \
  --end-date 2026-03-10 \
  --output json
```

Agent 规则：优先使用产品代码，不要优先用产品名称。名称可能有歧义，产品代码更稳定。

## 9. 行情录入

`quote` 通过 RMS3 后端写入行情录入记录，适合行情覆盖，不适合交易生命周期管理。

创建草稿：

```bash
uvx agent-rms quote draft \
  --instrument-code IRS_5Y_PAY \
  --template irs \
  --last-price 1.9200 \
  --bid-price 1.9100 \
  --ask-price 1.9300 \
  --output json
```

直接提交并生效：

```bash
uvx agent-rms quote submit \
  --instrument-code BOND_240210 \
  --template bond \
  --last-yield 1.8800 \
  --cover-minutes 15 \
  --output json
```

确认草稿：

```bash
uvx agent-rms quote confirm --entry-id 18 --output json
```

查看录入记录：

```bash
uvx agent-rms quote list --instrument-code IRS_5Y_PAY --output json
```

查看当前有效行情：

```bash
uvx agent-rms quote effective --instrument-code IRS_5Y_PAY --output json
```

字段规则：

- `--template irs` 必须提供 `--last-price`
- `--template bond` 必须提供 `--last-yield`
- `--bid-price`、`--ask-price`、`--last-clean-price` 可选
- `--cover-minutes` 默认是 `10`
- `--source` 默认是 `agent`

## 10. 期货手工交易

`trade` 只覆盖 RMS3 后端已有的期货手工交易接口，不处理 IRS 或现券交易。

创建期货手工交易：

```bash
uvx agent-rms trade create \
  --product-code PROD001 \
  --trade-code FUT_AGENT_001 \
  --instrument-code T2606 \
  --account-code ACC001 \
  --strategy-code STR001 \
  --trade-time 2026-06-16T09:30:00+08:00 \
  --price 101.25 \
  --quantity 2 \
  --output json
```

修改当日未结算期货交易：

```bash
uvx agent-rms trade update \
  --product-code PROD001 \
  --trade-code FUT_AGENT_001 \
  --instrument-code TF2606 \
  --account-code ACC002 \
  --strategy-code STR002 \
  --trade-time 2026-06-16T13:15:00+08:00 \
  --price 102.75 \
  --quantity -3 \
  --output json
```

删除当日未结算期货交易：

```bash
uvx agent-rms trade delete \
  --product-code PROD001 \
  --trade-code FUT_AGENT_001 \
  --yes \
  --output json
```

本地校验规则：

- 代码字段不能为空或纯空格
- `price` 必须大于 `0`
- `quantity` 不能为 `0`
- `quantity` 为正数表示买入，为负数表示卖出
- `trade-time` 必须带 timezone，例如 `2026-06-16T09:30:00+08:00`
- 删除必须显式传 `--yes`

后端生命周期规则：

- 只支持期货合约
- 修改和删除只允许当日成交
- 已结算期货成交不能修改或删除
- 需要 `create_trade` 权限和产品访问范围

Agent 安全规则：删除前必须确认准确的 `trade_code`，不要猜测成交编号。

## 11. 推荐工作流

只读诊断：

```bash
uvx agent-rms auth whoami --output json
uvx agent-rms portfolio overview --output json
uvx agent-rms market all --output json
```

曲线分析：

```bash
uvx agent-rms market future_curve --output json
uvx agent-rms market swap_curve --output json
uvx agent-rms market asw_curve --output json
```

行情覆盖：

```bash
uvx agent-rms quote draft ... --output json
uvx agent-rms quote list --instrument-code <instrument-code> --output json
uvx agent-rms quote confirm --entry-id <entry-id> --output json
uvx agent-rms quote effective --instrument-code <instrument-code> --output json
```

期货手工交易：

```bash
uvx agent-rms auth whoami --output json
uvx agent-rms portfolio detail --name <product-code> --output json
uvx agent-rms trade create ... --output json
```

修改或删除交易前，先从 RMS3 页面或经批准的后端查询确认目标成交，再调用
`trade update` 或 `trade delete --yes`。

## 12. 错误处理

命令非零退出时：

1. 不要把 stdout 当成功 JSON 解析。
2. 读取错误文本。
3. 根据错误建议修正输入或刷新登录态。
4. 只有在输入、权限或后端状态变化后才重试。

未找到凭证：

```text
未找到 profile=default 的登录凭证
```

处理：

```bash
uvx agent-rms auth login ...
```

token 失效：

```text
Invalid or expired token
```

处理：

```bash
uvx agent-rms auth login ...
```

组合名歧义：

```text
组合名称存在歧义，请使用产品代码
```

处理：

- 使用产品代码重新执行

历史期货交易修改或删除失败：

```text
Only same-day futures trades can be modified
```

处理：

- 查询当日成交
- 不要修改历史成交
- 业务需要调整时，录入新的更正成交

已结算期货交易修改或删除失败：

```text
Settled futures trades cannot be modified
```

处理：

- 不要重复提交同一修改或删除
- 使用已批准的调整流程

通过 `trade` 操作非期货交易：

```text
Only FUTURE trades are supported
```

处理：

- `trade` 只用于期货合约
- 不要用它处理 IRS 生命周期

## 13. 审计记录

每次写操作成功后，Agent 任务日志应保存：

- 命令名
- 去除敏感信息后的命令参数
- 输出里的 `source`
- 输出里的 `request`
- 输出里的 `data`
- 输出里的 `ts`

写操作失败时，Agent 任务日志应保存：

- 命令名
- 去除敏感信息后的参数
- 退出码
- 错误信息
- 已尝试的修正动作

永远不要记录：

- 明文密码
- bearer token
- 凭证文件内容

## 14. 快速参考

```bash
uvx agent-rms --help
uvx agent-rms auth --help
uvx agent-rms market --help
uvx agent-rms history --help
uvx agent-rms portfolio --help
uvx agent-rms quote --help
uvx agent-rms trade --help
```

命令帮助是当前安装版本的最终入口说明。
