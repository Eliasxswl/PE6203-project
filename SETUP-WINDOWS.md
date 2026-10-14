# Windows 与 BigModel 配置

本地源码 commit：888c779a0fe735f612ca62bdd1fdd7c9e6bf8701。
Python 3.12.14，1mcp 0.39.1，模型 API 模式。依赖锁定在 requirements-api.lock.txt。

## 已完成

- 在项目内建立 .venv，安装 requirements-api.txt 的轻量依赖；未安装完整 GPU 依赖表。
- 在 .runtime 安装 @1mcp/agent；未修改全局 npm 安装。
- 下载 README 链接中的 original_servers.zip、iter3_servers.zip、iter5_servers.zip，并解压到 servers 下。
- 核对压缩包与磁盘文件；每套原生 tar 漏掉一个 snow ☃ 测试目录的 index.html，已使用 Python 补齐。记录见 logs/archive-audit.json。
- 生成 config/local/original.json、iter3.json、iter5.json 的本机路径。原始配置文件不改动；69 个可匹配的 Early npx 入口改用下载的原始快照，避免这部分工具运行最新 npm 版本。
- 去掉 API 模式的 FastChat 强制导入和 Windows 不支持的 pty 导入。
- Agent 和评分器共享环境变量配置；没有写入 API key。
- 评分器缺失的 JSON 解析导入已替换；缺失的 real.json 改成显式 --task_selection 参数。
- 使用 python -m 入口，避免 Windows 执行嵌套脚本时找不到 custom 包。
- 已验证 Agent / MCP / judge 导入、CLI --help 和 pip check。
- 真实本地 MCP 验证：下载包中的 sequential-thinking，Early 发现 1 个工具，Middle 2 个，Late 3 个；Early 的真实工具调用成功。完整 Schema 见 logs/tools-*.json。

这只是基础设施和少量工具验证，不代表所有服务器或全量任务已通过。尚未调用大模型、跑正式任务或进行 LLM 评分。

## 智谱官方地址

普通 API 的 OpenAI 兼容 base URL：

https://open.bigmodel.cn/api/paas/v4/

实际 chat completions 地址为 https://open.bigmodel.cn/api/paas/v4/chat/completions 。
官方说明：https://docs.bigmodel.cn/cn/guide/develop/openai/introduction 。
已读取官方 .md 文档，项目内保存 bigmodel-openai-doc.md。
这里按普通 API 配置，不默认套用 Coding Plan 地址或套餐额度。

## 持久化本地配置

项目根目录已有 .env。直接编辑此文件即可，关闭终端不会丢失；Agent、评分器和 check_model.py 会自动读取。已有进程环境变量优先于文件，方便部署时覆盖配置。

```dotenv
BIGMODEL_API_KEY=在这里填写你的key
BIGMODEL_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
BIGMODEL_MODEL=填写你账号可用且支持工具调用的模型ID
BIGMODEL_JUDGE_MODEL=填写本次实验固定的评分模型ID
BENCH_JUDGE_RUNS=5
PYTHONUTF8=1
```

BIGMODEL_JUDGE_MODEL 留空时，开发阶段使用 BIGMODEL_MODEL。正式实验固定评分模型和设置。
.env 和 .env.* 已忽略，只有无密钥的 .env.example 进入 Git。新机器复制 .env.example 为 .env 后填写即可。不要把 key 放进 experiment.json 或报告。

## 先做两次小型模型验证

下面每条命令会发起一次真实模型请求，可能计费；没有自动运行：

```powershell
& .venv\Scripts\python.exe scripts\check_model.py
& .venv\Scripts\python.exe scripts\check_model.py --tool-call
```

第一条验证认证和文字输出；第二条验证 function calling；打印响应与 usage，不打印 key。

## 本地工具验证

启动单工具服务，不调用模型。每条启动命令占用一个终端；Ctrl+C 停止。

```powershell
& .\scripts\start_mcp.ps1 -Stage smoke -Port 3050
& .\scripts\start_mcp.ps1 -Stage smoke-iter3 -Port 3053
& .\scripts\start_mcp.ps1 -Stage smoke-iter5 -Port 3055
```

在另一终端发现工具：

```powershell
& .venv\Scripts\python.exe scripts\probe_mcp.py --url http://127.0.0.1:3050/mcp
& .venv\Scripts\python.exe scripts\probe_mcp.py --url http://127.0.0.1:3053/mcp
& .venv\Scripts\python.exe scripts\probe_mcp.py --url http://127.0.0.1:3055/mcp
```

smoke 配置只含 sequential-thinking，不足以运行正式基准任务。这个例子用于确认客户端、1mcp 和服务器之间的链路。

## 正式运行前的检查

1. 根据选中的少量任务生成对应服务器子集配置。完整配置有 167 个条目，不建议一开始全部启动。
2. 部分剩余 npx 条目仍使用 npm 服务，需要联网下载并检查版本固定。Python 工具通过项目内 uv/uvx 运行，首次使用可能下载额外环境。
3. 工具快照含 Linux 环境依赖；虽然上述 Node 工具已在 Windows 验证，其他工具可能需要浏览器、数据库、系统依赖或外部网络。
4. chosen_idx.json 的 201 个 ID 都在 test_cases.json 中，但它是否等同评分器缺失的 real.json、是否为课程指定列表，尚未确认。开发可以使用显式子集，最终实验需核对。
5. Middle/Late 的 mutation_path、任务变化标注和实际工具版本必须匹配，不应靠目录名猜测。
6. 每次实验重置任务文件和状态；三策略知识更新层、成本记录与实验隔离尚未实现。
7. 评分器现固定每条轨迹尝试 5 次，失败也计入次数，不补跑；API 模式自动重试关闭，重启评分复用已记录的五次尝试。失败次数和有效评分数必须报告。
8. config/experiment.json 规定任务重复运行 3 次。这是实验协议，三次任务的调度、独立初始状态恢复与跨重复结果汇总仍待实现，不能把单次任务脚本说成已经自动运行三次。
9. 任务运行三次和同一轨迹评分五次是两层重复；全部采用时，每个任务/版本/策略有 3 条轨迹、15 次 judge 请求，另加 Agent 的多步模型调用。

启动完整某阶段配置的形式如下；建议先把配置裁剪为任务所需服务器：

```powershell
& .\scripts\start_mcp.ps1 -Stage original -Port 3050
```

运行器的形式如下，TaskFile 必须显式给出，防止无意跑全量任务：

```powershell
& .\scripts\run_agent.ps1 -TaskFile 'custom/data/test_cases/你的开发子集.json' -Stage original
```

评分时从 src 目录使用模块入口：

```powershell
$env:PYTHONPATH = 'E:\NTU Learn\PE6203\part2\MCPEvol-Bench\src'
Set-Location -LiteralPath 'E:\NTU Learn\PE6203\part2\MCPEvol-Bench\src'
& ..\.venv\Scripts\python.exe -m custom.analysis.answer.evaluation --answer_path 'custom/data/local_output/模型ID/ANSWER' --task_selection 'custom/data/test_cases/你的任务选择文件.json' --num_runs 5 --max-workers 1
```

task_selection 的格式为 {"samples":[{"idx":任务ID}]}。任务运行文件为 test_cases.json 格式的记录数组。

## 重建

```powershell
& .venv\Scripts\python.exe -m pip install -r requirements-api.lock.txt
npm.cmd install --prefix .runtime @1mcp/agent@0.39.1
& .venv\Scripts\python.exe scripts\prepare_local_config.py
```

机器路径、下载包、已解压工具、日志、.venv、.runtime 和 .env 均已加入 .gitignore。
