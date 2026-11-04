# 开发指南

## 日常入口

| 任务 | 操作 |
|---|---|
| 正式使用工具 | 双击 `启动.bat`，使用原有正式数据库 |
| 开发 Python 和画布 | 双击 `开发.bat`，默认打开 `http://127.0.0.1:8510` |
| 快速检查 | 双击 `检查.bat` |
| 完整回归 | `.venv\Scripts\python.exe scripts/dev.py check --frontend --ui` |
| 生成演示库 | `.venv\Scripts\python.exe scripts/dev.py demo` |
| 生成发布版画布 | `.venv\Scripts\python.exe scripts/dev.py build` |

开发默认使用 `.dev/demo.db`，首次启动自动生成“开发演示车”，包含需求、SL/LC/AF 功能层级、追溯链、5 条信号和多个接收 ECU。再次启动保留演示库内的修改。侧边栏选择“开发演示车”即可查看场景。

如需一个全新场景，指定新文件名：

```powershell
.venv\Scripts\python.exe scripts/dev.py serve --db .dev/scenario-02.db
```

开发工具拒绝把项目中的 `ee_req.db` 或未标记为开发演示的现有数据库用作种子库。检查命令会为浏览器测试新建临时演示库，并在退出后清理。

## 首次准备环境

使用 Python 3.11 和 Node.js 22：

```powershell
python scripts/dev.py setup --frontend
.venv\Scripts\python.exe -m playwright install chromium
```

`requirements.txt` 表达依赖范围；`requirements.lock` 记录本项目验证过的 Windows/Python 3.11 运行依赖快照；`requirements-dev.txt` 再加入固定版本的测试工具。前端用 `npm ci` 按 `package-lock.json` 安装。

已有 Python 环境更新时，运行：

```powershell
.venv\Scripts\python.exe scripts/dev.py setup --frontend
```

依赖升级应单独提交，安装后检查依赖冲突并跑完整回归，再更新版本快照。

## 热更新与端口

开发入口同时管理两个本地进程：Streamlit 为 8510，Vite 为 5173。修改 Python 后 Streamlit 重新运行；修改画布 `src/` 后由 Vite 热更新，无须每次 `npm run build`。Ctrl+C 会停止两个子进程。开发服务只监听本机。

```powershell
.venv\Scripts\python.exe scripts/dev.py serve --port 8511 --component-port 5174
```

无须改画布或未安装 Node.js 时：

```powershell
.venv\Scripts\python.exe scripts/dev.py serve --built
```

`EE_REQ_COMPONENT_DEV_URL` 指定 Streamlit 组件的开发服务地址；未设置时使用 `signal_flow_component/dist/`。发布版保留编译资源，使用者无须启动 Vite。

## 模块规则

新页面写入 `workspaces/`。校验、解析、审计和业务计算写入 `services/`，由页面调用；不要把数据库写入放到前端。

当前已拆出信号端点、需求层级策略、追溯计算、DBC 解析和通信矩阵页面。`app.py` 中剩余的旧页面可按功能逐步迁出，无需一次重写整个应用。

需求保存和端点变更必须继续检查当前车型和编辑权。涉及业务对象的测试均使用临时库；不要导入本机 MEV02 数据来让自动化测试通过。

## 验证范围

`check` 检查 Python 语法、关键 Ruff 规则和单元测试，包含旧表迁移、车型隔离、审计与协作锁。Ruff 先建立无致命问题的统一基线，后续按模块逐步收紧风格规则。

`--frontend` 增加画布状态测试和发布构建；`--ui` 启动独立服务，验证演示车型、需求规范、信号单选、视图位置、多接收 ECU 新增/删除、通信矩阵比较和 CSV 下载。浏览器截图写入 `test-results/`。

加 `--ui --hot` 可以对 Vite 开发画布运行同一组浏览器回归。默认使用 Playwright Chromium；也可通过 `EE_REQ_TEST_BROWSER` 指定已安装浏览器的可执行文件路径。

新浏览器测试只依赖生成的演示数据、动态端口和 Playwright Chromium。`tests/playwright_*.py` 保留为旧的本机专项复现脚本，部分仍需要原始 MEV02 场景；它们不在可移植的自动回归入口中。

GitHub Actions 配置在 `.github/workflows/check.yml`，推送或提 PR 后运行完整回归并保存截图。配置文件写入本地不代表云端检查已经运行。
