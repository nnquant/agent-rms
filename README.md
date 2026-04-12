# agent-rms

面向 AI Agent 的独立 RMS 数据 CLI 包。

推荐使用方式：
```bash
git clone <repo-url>
cd agent-rms
uv tool install .
uvx agent-rms --help
```

对于 Agent 场景，推荐统一通过 `uvx agent-rms ...` 调用。
这样可以避免依赖当前 shell 是否激活虚拟环境，同时保持调用入口稳定。

提供以下能力：
- `agent-rms auth`：登录与本地凭证管理
- `agent-rms market`：最新市场数据（all/future/swap/future_curve/swap_curve/asw_curve）
- `agent-rms quote`：行情录入与有效行情查询（draft/submit/confirm/list/effective）
- `agent-rms history`：历史数据查询
- `agent-rms portfolio`：组合数据（overview/detail/exposure/performance）

独立使用指南见 [USAGE.md](./USAGE.md)。
