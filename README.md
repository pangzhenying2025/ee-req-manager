# EE Requirements & Architecture Manager

面向汽车 E/E 架构师、系统工程师和 DRE 的轻量级需求工程平台。产品思路参考 IBM DOORS/DOORS Next，以“需求”为核心，把整车需求、功能分解、控制器分配、CAN 接口和验证关系组织成可追溯的工程链路。

## 核心闭环

```text
利益相关方需求 → 整车需求 → 功能/系统/安全需求
                                  ↓
                           逻辑功能与 ECU
                                  ↓
                          CAN 报文与信号接口
                                  ↓
                            验证需求与测试
```

## 功能

### 需求工程

- DOORS 风格的结构化需求规范（Module）
- Stakeholder、Vehicle、Functional、System、Safety、Interface、Verification 需求类型
- 需求层级、状态、优先级、ASIL、负责人、来源和验证方法
- 修改原因、字段级变更历史和需求版本号
- 车型内唯一编号与严格的数据隔离

### 架构追溯

- 需求、功能和信号之间的双向追溯
- 来源、分解、满足、分配、验证、依赖和冲突关系
- 自动检查缺少上游来源、架构分配和验证链路的需求
- 需求追溯完整率与覆盖矩阵

### 配置与基线

- 冻结需求、功能、信号和追溯链路的里程碑快照
- 基线对象浏览
- 需求字段级审计历史

### 知识与质量评审

- 内置需求质量门禁：义务措辞、原子性、歧义、来源、验证方法和验收准则
- 功能、接口、安全和验证需求写作模板
- 通用 E/E、ISO 26262、Automotive SPICE 与 SOTIF 追踪蓝图
- 经官方入口校正的标准版本目录和明确的合规边界
- 固定上游知识仓库提交，记录提炼来源并避免直接采用未经验证的覆盖率声明

### 汽车 E/E 架构

- 车辆功能、ECU 归属、优先级、状态和 ASIL 管理
- CAN 信号、报文、位布局、精度、偏移和字节序管理
- 功能—信号绑定和功能逻辑关系图
- DOORS 风格的可编辑信号数据流画布：报文聚合、一个信号多接收 ECU、新增/移动/删除/恢复端点、变更审计和 PNG 导出
- DBC 文件与 Excel 通讯矩阵导入
- 多车型项目、基础车型借用和数据隔离
- CSV 数据导出

## 快速启动

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```

也可以直接双击 `启动.bat`。默认地址为 <http://localhost:8501>。

### 局域网多人协作

双击 `启动.bat` 后，脚本会等待服务就绪并自动打开本机浏览器，同时在窗口中显示本机地址和局域网地址，例如：

```text
Local URL: http://127.0.0.1:8501
LAN URL:   http://192.168.1.20:8501
```

同一局域网中的其他成员用浏览器打开 `LAN URL` 即可。每位成员应在左侧填写自己的“协作者名称”。系统会显示同一车型的在线成员，并对需求、功能、信号和信号数据流使用 5 分钟编辑权，避免多人同时保存时互相覆盖。编辑完成后可以主动释放；保存需求、功能或信号后会自动释放。

如果其他电脑无法连接，请确认 Windows 网络类型为“专用网络”，并允许 TCP 8501 端口通过防火墙。该模式面向可信局域网，不应直接暴露到互联网。

数据库默认保存在项目目录的 `ee_req.db`。测试或多实例部署时可通过环境变量指定独立数据库：

```powershell
$env:EE_REQ_DB_PATH = "D:\data\ee-project.db"
streamlit run app.py
```

## 页面结构

| 工作区 | 用途 |
|---|---|
| 工程总览 | 当前车型的需求、功能、信号和追溯状态 |
| 需求规范 | 新建规范、编写需求、层级组织和版本编辑 |
| 需求追溯 | 建立需求—需求—功能—信号链路并检查覆盖 |
| 基线与变更 | 冻结里程碑配置并查看审计记录 |
| 知识与评审 | 批量质量门禁、单条评审、模板、追踪蓝图和标准目录 |
| 功能与接口 | 管理功能、逻辑关系、信号和导入数据 |
| 车型管理 | 创建车型、借用基础数据和保持项目隔离 |

## 数据安全

- SQLite 连接默认启用外键约束。
- 所有业务读取、编辑和删除操作按当前车型限制范围。
- 旧版全局唯一约束迁移前自动生成 `*.pre_v04_backup` 备份。
- 旧表迁移显式映射字段，不使用有错列风险的 `SELECT *`。

## 验证

```powershell
python -m py_compile app.py db.py i18n.py requirements_ui.py automotive_knowledge.py requirements_knowledge_ui.py
ruff check app.py db.py requirements_ui.py automotive_knowledge.py requirements_knowledge_ui.py
python -m unittest discover -s tests -v
```

当前自动化测试覆盖外键、车型隔离、追溯/基线写入和旧数据库安全迁移。

## 技术栈

- Streamlit
- SQLite + SQLAlchemy
- Pandas
- cantools
- openpyxl
- vis-network

## License

MIT
