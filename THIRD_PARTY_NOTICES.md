# Third-party notices

EE-Req Manager 本身采用 MIT License。下列开源项目用于运行、构建，或作为明确标注的设计参考；各项目仍受其自身许可证约束。

| 项目 | 用途 | 许可证 | 集成状态 |
|---|---|---|---|
| StrictDoc | 需求层级、字段模型、追溯和交换设计参考 | Apache-2.0 | 仅参考公开设计思想，未复制或打包其代码 |
| React Flow (`@xyflow/react`) | 可编辑信号数据流画布 | MIT | 前端运行依赖 |
| ELK (`elkjs`) | ECU—信号—ECU 图自动布局 | EPL-2.0 | 前端运行依赖 |
| cantools | DBC 解析及 CAN 信号工程属性读取 | MIT | Python 运行依赖 |
| canmatrix | DBC/XLSX/DBF/SYM/JSON 统一读取和版本比较 | BSD-2-Clause | Python 运行依赖 |
| Streamlit | Web 应用框架 | Apache-2.0 | Python 运行依赖 |
| SQLAlchemy | SQLite 数据访问 | MIT | Python 运行依赖 |
| Pandas | 表格处理和差异导出 | BSD-3-Clause | Python 运行依赖 |
| openpyxl | Excel 读取 | MIT | Python 运行依赖 |
| vis-network | 现有功能关系图和 Excel 预览图 | Apache-2.0 / MIT | 浏览器运行依赖，后续迁移到本地构建 |

仓库提交前应保留本文件、根目录 `LICENSE`、前端 lockfile 及依赖包自身携带的版权/许可证文本。该清单是工程治理记录，不是法律意见。
