"""
EE-Req Manager — 数据模型与数据库管理
汽车电子电气架构需求管理工具
v0.3: 新增车型管理，支持数据隔离和借用
"""
import json
import os
import shutil
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DB_PATH = os.environ.get(
    "EE_REQ_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "ee_req.db"),
)
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={"timeout": 30, "check_same_thread": False},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """Prepare every SQLite connection for concurrent LAN editing."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# ========== 车型项目表 ==========
class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)  # 车型名称 如 MEV02
    code = Column(String(50))                                  # 车型代码
    description = Column(Text)                                 # 车型描述
    base_project_id = Column(Integer, ForeignKey("projects.id"))  # 借用来源车型
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    base_project = relationship("Project", remote_side=[id])
    functions = relationship("Function", back_populates="project")
    signals = relationship("Signal", back_populates="project")


# ========== 车辆功能表 ==========
class Function(Base):
    __tablename__ = "functions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1)  # 所属车型
    name = Column(String(100), nullable=False)
    func_id = Column(String(50), nullable=False)               # 功能编号 如 FUNC-001
    category = Column(String(50))                              # 功能域
    module = Column(String(50))                                # 归属ECU
    description = Column(Text)
    priority = Column(String(20), default="Medium")
    status = Column(String(20), default="Draft")
    asil_level = Column(String(10))
    source_project_id = Column(Integer)                        # 借用来源车型ID（非空=借用）
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('func_id', 'project_id', name='uq_func_id_project'),
    )

    # 关系
    project = relationship("Project", back_populates="functions")
    signal_links = relationship("FunctionSignal", back_populates="function", cascade="all, delete-orphan")
    source_rels = relationship("FuncRelation", foreign_keys="FuncRelation.source_id",
                               back_populates="source", cascade="all, delete-orphan")
    target_rels = relationship("FuncRelation", foreign_keys="FuncRelation.target_id",
                               back_populates="target", cascade="all, delete-orphan")


# ========== CAN信号表 ==========
class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1)
    name = Column(String(100), nullable=False)
    signal_id = Column(String(50), nullable=False)             # 信号编号 SIG-001
    message_name = Column(String(100))
    message_id = Column(String(20))
    dlc = Column(Integer)
    start_bit = Column(Integer)
    bit_length = Column(Integer)
    factor = Column(Float, default=1.0)
    offset = Column(Float, default=0.0)
    min_value = Column(Float)
    max_value = Column(Float)
    unit = Column(String(20))
    byte_order = Column(String(10), default="Motorola")
    value_type = Column(String(10), default="Unsigned")
    cycle_time = Column(Integer)
    module = Column(String(50))
    description = Column(Text)
    source_project_id = Column(Integer)                        # 借用来源车型ID
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('signal_id', 'project_id', name='uq_signal_id_project'),
    )

    # 关系
    project = relationship("Project", back_populates="signals")
    func_links = relationship("FunctionSignal", back_populates="signal", cascade="all, delete-orphan")


# ========== 功能-信号关联表 ==========
class FunctionSignal(Base):
    __tablename__ = "function_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    function_id = Column(Integer, ForeignKey("functions.id"), nullable=False)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=False)
    direction = Column(String(10), nullable=False)             # Input / Output / Feedback
    usage_desc = Column(Text)
    is_required = Column(Boolean, default=True)

    function = relationship("Function", back_populates="signal_links")
    signal = relationship("Signal", back_populates="func_links")


# ========== 功能间逻辑关系表 ==========
class FuncRelation(Base):
    __tablename__ = "func_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1)
    source_id = Column(Integer, ForeignKey("functions.id"), nullable=False)
    target_id = Column(Integer, ForeignKey("functions.id"), nullable=False)
    rel_type = Column(String(30))
    description = Column(Text)
    conditions = Column(Text)                                  # JSON格式条件树
    source_project_id = Column(Integer)                        # 借用来源车型ID

    source = relationship("Function", foreign_keys=[source_id], back_populates="source_rels")
    target = relationship("Function", foreign_keys=[target_id], back_populates="target_rels")


# ========== 信号-功能关系表 ==========
class SignalFuncRelation(Base):
    __tablename__ = "signal_func_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=False)
    func_id = Column(Integer, ForeignKey("functions.id"), nullable=False)
    direction = Column(String(20), nullable=False)            # signal_to_func / func_to_signal
    rel_type = Column(String(30), default="触发")              # 触发/报警/联动/互锁
    conditions = Column(Text)                                 # JSON条件树
    description = Column(Text)
    source_project_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    signal = relationship("Signal")
    function = relationship("Function")


# ========== 信号数据流端点与架构变更审计 ==========
class SignalEndpoint(Base):
    """A normalized Tx/Rx endpoint while preserving the original DBC ECU."""
    __tablename__ = "signal_endpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    signal_id = Column(Integer, ForeignKey("signals.id", ondelete="CASCADE"), nullable=False)
    endpoint_role = Column(String(10), nullable=False)          # Tx / Rx
    dbc_ecu_name = Column(String(100))                          # DBC 原始端点（不可覆盖）
    ecu_name = Column(String(100), nullable=False)              # 当前项目中的有效端点
    function_id = Column(Integer, ForeignKey("functions.id", ondelete="SET NULL"))
    source_kind = Column(String(20), default="DBC", nullable=False)  # DBC / Manual
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    signal = relationship("Signal")
    function = relationship("Function")
    __table_args__ = (
        UniqueConstraint(
            "project_id", "signal_id", "endpoint_role", "dbc_ecu_name",
            name="uq_signal_endpoint_dbc_source",
        ),
    )


class ArtifactChangeRecord(Base):
    """Field-level audit trail for architecture artifacts outside requirements."""
    __tablename__ = "artifact_change_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    artifact_type = Column(String(40), nullable=False)
    artifact_id = Column(Integer, nullable=False)
    change_type = Column(String(30), nullable=False)
    field_name = Column(String(50))
    old_value = Column(Text)
    new_value = Column(Text)
    reason = Column(Text, nullable=False)
    changed_by = Column(String(100))
    changed_at = Column(DateTime, default=datetime.utcnow)


# ========== 系统配置表 ==========
class SysConfig(Base):
    __tablename__ = "sys_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(50), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ========== 需求工程核心模型 ==========
class RequirementModule(Base):
    """A DOORS-like specification/module containing ordered requirements."""
    __tablename__ = "requirement_modules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    status = Column(String(20), default="Draft")
    owner = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("code", "project_id", name="uq_module_code_project"),)
    requirements = relationship("Requirement", back_populates="module", cascade="all, delete-orphan")


class Requirement(Base):
    """A versioned requirement artifact that can be allocated and traced."""
    __tablename__ = "requirements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    module_id = Column(Integer, ForeignKey("requirement_modules.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(Integer, ForeignKey("requirements.id", ondelete="SET NULL"))
    req_id = Column(String(50), nullable=False)
    title = Column(String(250), nullable=False)
    text = Column(Text, nullable=False)
    req_type = Column(String(40), default="Functional")
    req_level = Column(String(30), default="System")
    req_nature = Column(String(30), default="Functional")
    status = Column(String(20), default="Draft")
    priority = Column(String(20), default="Medium")
    asil_level = Column(String(10))
    owner = Column(String(100))
    source = Column(String(250))
    rationale = Column(Text)
    verification_method = Column(String(50))
    acceptance_criteria = Column(Text)
    sort_order = Column(Integer, default=0)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("req_id", "project_id", name="uq_req_id_project"),)
    module = relationship("RequirementModule", back_populates="requirements")
    parent = relationship("Requirement", remote_side=[id])


class TraceLink(Base):
    """Typed, bidirectional trace between requirements and architecture artifacts."""
    __tablename__ = "trace_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(String(30), nullable=False)
    source_id = Column(Integer, nullable=False)
    target_type = Column(String(30), nullable=False)
    target_id = Column(Integer, nullable=False)
    link_type = Column(String(30), nullable=False)
    description = Column(Text)
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "source_type", "source_id", "target_type", "target_id", "link_type",
            name="uq_trace_link",
        ),
    )


class Baseline(Base):
    __tablename__ = "baselines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("name", "project_id", name="uq_baseline_name_project"),)
    items = relationship("BaselineItem", back_populates="baseline", cascade="all, delete-orphan")


class BaselineItem(Base):
    __tablename__ = "baseline_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    baseline_id = Column(Integer, ForeignKey("baselines.id", ondelete="CASCADE"), nullable=False)
    artifact_type = Column(String(30), nullable=False)
    artifact_id = Column(Integer, nullable=False)
    snapshot = Column(Text, nullable=False)

    baseline = relationship("Baseline", back_populates="items")
    __table_args__ = (
        UniqueConstraint("baseline_id", "artifact_type", "artifact_id", name="uq_baseline_artifact"),
    )


class ChangeRecord(Base):
    __tablename__ = "change_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    requirement_id = Column(Integer, ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False)
    change_type = Column(String(30), nullable=False)
    field_name = Column(String(50))
    old_value = Column(Text)
    new_value = Column(Text)
    reason = Column(Text)
    changed_by = Column(String(100))
    changed_at = Column(DateTime, default=datetime.utcnow)


# ========== 局域网协作会话与编辑权 ==========
class CollaborationSession(Base):
    """A browser session visible to collaborators on the same project."""
    __tablename__ = "collaboration_sessions"

    session_id = Column(String(64), primary_key=True)
    user_name = Column(String(100), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    page_name = Column(String(100))
    ip_address = Column(String(64))
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EditLock(Base):
    """Short-lived project-scoped edit ownership for mutable artifacts."""
    __tablename__ = "edit_locks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    artifact_type = Column(String(40), nullable=False)
    artifact_id = Column(Integer, nullable=False)
    session_id = Column(String(64), nullable=False)
    user_name = Column(String(100), nullable=False)
    acquired_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "artifact_type", "artifact_id",
            name="uq_edit_lock_artifact",
        ),
    )


# ========== 配置读写工具函数 ==========
def get_config(session, key, default=None):
    row = session.query(SysConfig).filter_by(key=key).first()
    if row:
        try:
            return json.loads(row.value)
        except (json.JSONDecodeError, TypeError):
            return row.value
    return default


def set_config(session, key, value):
    row = session.query(SysConfig).filter_by(key=key).first()
    json_val = json.dumps(value, ensure_ascii=False)
    if row:
        row.value = json_val
        row.updated_at = datetime.utcnow()
    else:
        row = SysConfig(key=key, value=json_val)
        session.add(row)
    session.commit()


def seed_default_configs(session):
    defaults = {
        "ecu_list": ["VCU", "BCM", "ICM/仪表", "ADDC", "GW", "CCU", "BMS", "MCU", "ESC", "EPS", "其他"],
        "category_list": ["车身", "动力", "底盘", "座舱", "热管理", "ADAS", "网关", "充电", "其他"],
        "priority_list": ["High", "Medium", "Low"],
        "status_list": ["Draft", "Review", "Approved", "Released"],
        "asil_list": ["-", "QM", "ASIL-A", "ASIL-B", "ASIL-C", "ASIL-D"],
    }
    for k, v in defaults.items():
        if not session.query(SysConfig).filter_by(key=k).first():
            session.add(SysConfig(key=k, value=json.dumps(v, ensure_ascii=False)))
    session.commit()


def ensure_default_project(session):
    """确保默认车型存在，返回其ID"""
    default = session.query(Project).filter_by(name="通用").first()
    if not default:
        default = Project(name="通用", code="DEFAULT", description="默认车型（历史数据迁移用）")
        session.add(default)
        session.commit()
    return default.id


# ========== 建表 + 自动迁移 ==========
def init_db():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_default_configs(db)
        default_pid = ensure_default_project(db)

        # 自动迁移
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 获取所有现有表的列
        def get_cols(table):
            try:
                cursor.execute(f"PRAGMA table_info({table})")
                return [c[1] for c in cursor.fetchall()]
            except sqlite3.DatabaseError:
                return []

        # 自动迁移：新增 signal_func_relations 表
        new_table_sql = """
            CREATE TABLE IF NOT EXISTS signal_func_relations (
                id INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL DEFAULT 1,
                signal_id INTEGER NOT NULL,
                func_id INTEGER NOT NULL,
                direction VARCHAR(20) NOT NULL,
                rel_type VARCHAR(30) DEFAULT '触发',
                conditions TEXT,
                description TEXT,
                source_project_id INTEGER,
                created_at DATETIME,
                FOREIGN KEY(signal_id) REFERENCES signals(id),
                FOREIGN KEY(func_id) REFERENCES functions(id),
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
        """
        cursor.execute(new_table_sql)
        conn.commit()

        # 给各表加 project_id 列
        for table in ["functions", "signals", "func_relations"]:
            cols = get_cols(table)
            if "project_id" not in cols:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN project_id INTEGER DEFAULT {default_pid}")
                conn.commit()
            if "source_project_id" not in cols:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN source_project_id INTEGER")
                conn.commit()

        # func_relations 加 conditions 列
        rel_cols = get_cols("func_relations")
        if "conditions" not in rel_cols:
            cursor.execute("ALTER TABLE func_relations ADD COLUMN conditions TEXT")
            conn.commit()

        # 需求的抽象层级与工程性质是两个独立维度。保留 req_type 兼容旧版，
        # 新页面与统计使用 req_level / req_nature，避免把“系统层”和“功能性”混为一谈。
        req_cols = get_cols("requirements")
        if "req_level" not in req_cols:
            cursor.execute("ALTER TABLE requirements ADD COLUMN req_level VARCHAR(30)")
        if "req_nature" not in req_cols:
            cursor.execute("ALTER TABLE requirements ADD COLUMN req_nature VARCHAR(30)")
        cursor.execute("""
            UPDATE requirements
            SET req_level = CASE
                WHEN req_id LIKE 'VER-%' OR req_type = 'Verification' THEN 'Verification'
                WHEN req_id LIKE 'IF-%' OR req_type = 'Interface' THEN 'Interface'
                WHEN req_id LIKE 'FUN-SL%' THEN 'System'
                WHEN req_id LIKE 'SYS-LC%' THEN 'Subsystem'
                WHEN req_id LIKE 'SYS-AF%' THEN 'Function'
                WHEN req_id LIKE 'SYS-%' OR req_type IN ('System', 'Safety') THEN 'System'
                WHEN req_type = 'Stakeholder' THEN 'Stakeholder'
                WHEN req_type = 'Vehicle' THEN 'Vehicle'
                WHEN req_type = 'Functional' THEN 'Subsystem'
                ELSE 'System'
            END
            WHERE req_level IS NULL OR TRIM(req_level) = ''
        """)
        # MEV02 功能清单采用三级功能结构：SL 系统、LC 子系统、AF 具体功能。
        # 该修正规则需要覆盖已经由旧版本填写过的非空层级，且仅作用于 MEV02。
        cursor.execute("""
            UPDATE requirements
            SET req_level = CASE
                WHEN req_id LIKE 'FUN-SL%' THEN 'System'
                WHEN req_id LIKE 'SYS-LC%' THEN 'Subsystem'
                WHEN req_id LIKE 'SYS-AF%' THEN 'Function'
                ELSE req_level
            END
            WHERE project_id IN (SELECT id FROM projects WHERE code = 'MEV02')
              AND (req_id LIKE 'FUN-SL%' OR req_id LIKE 'SYS-LC%' OR req_id LIKE 'SYS-AF%')
        """)
        cursor.execute("""
            UPDATE requirements
            SET req_nature = CASE
                WHEN req_id = 'VEH-DBC-ROOT' THEN 'Interface'
                WHEN req_id LIKE 'VER-%' OR req_type = 'Verification' THEN 'Verification'
                WHEN req_id LIKE 'IF-%' OR req_type = 'Interface' THEN 'Interface'
                WHEN req_type = 'Safety' THEN 'Safety'
                ELSE 'Functional'
            END
            WHERE req_nature IS NULL OR TRIM(req_nature) = ''
        """)
        conn.commit()

        # 修复旧数据：project_id 为空的设为默认车型
        for table in ["functions", "signals", "func_relations"]:
            cursor.execute(f"UPDATE {table} SET project_id = {default_pid} WHERE project_id IS NULL")
        conn.commit()

        # 删除旧的全局唯一约束，改为 (xxx_id, project_id) 唯一
        # SQLite不支持DROP CONSTRAINT，需要重建表
        _migrate_unique_constraints(conn, cursor, default_pid)
    finally:
        if "conn" in locals():
            conn.close()
        db.close()


def _migrate_unique_constraints(conn, cursor, default_pid):
    """迁移唯一约束：从全局唯一改为按车型唯一"""
    def unique_indexes(table):
        result = []
        for row in cursor.execute(f"PRAGMA index_list({table})").fetchall():
            if row[2]:
                cols = [c[2] for c in cursor.execute(f"PRAGMA index_info('{row[1]}')").fetchall()]
                result.append(cols)
        return result

    has_old_unique = ["func_id"] in unique_indexes("functions")
    has_old_sig_unique = ["signal_id"] in unique_indexes("signals")

    if has_old_unique or has_old_sig_unique:
        backup_path = f"{DB_PATH}.pre_v04_backup"
        if not os.path.exists(backup_path):
            conn.commit()
            shutil.copy2(DB_PATH, backup_path)
        try:
            cursor.execute("BEGIN IMMEDIATE")
            if has_old_unique:
                # 重建 functions 表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS functions_new (
                        id INTEGER PRIMARY KEY,
                        project_id INTEGER NOT NULL DEFAULT 1,
                        name VARCHAR(100) NOT NULL,
                        func_id VARCHAR(50) NOT NULL,
                        category VARCHAR(50),
                        module VARCHAR(50),
                        description TEXT,
                        priority VARCHAR(20) DEFAULT 'Medium',
                        status VARCHAR(20) DEFAULT 'Draft',
                        asil_level VARCHAR(10),
                        source_project_id INTEGER,
                        created_at DATETIME,
                        updated_at DATETIME,
                        UNIQUE(func_id, project_id),
                        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                    )
                """)
                cursor.execute("""
                    INSERT INTO functions_new (
                        id, project_id, name, func_id, category, module, description,
                        priority, status, asil_level, source_project_id, created_at, updated_at
                    )
                    SELECT id, COALESCE(project_id, ?), name, func_id, category, module,
                           description, priority, status, asil_level, source_project_id,
                           created_at, updated_at
                    FROM functions
                """, (default_pid,))
                cursor.execute("DROP TABLE functions")
                cursor.execute("ALTER TABLE functions_new RENAME TO functions")

            if has_old_sig_unique:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS signals_new (
                        id INTEGER PRIMARY KEY,
                        project_id INTEGER NOT NULL DEFAULT 1,
                        name VARCHAR(100) NOT NULL,
                        signal_id VARCHAR(50) NOT NULL,
                        message_name VARCHAR(100),
                        message_id VARCHAR(20),
                        dlc INTEGER,
                        start_bit INTEGER,
                        bit_length INTEGER,
                        factor FLOAT DEFAULT 1.0,
                        offset FLOAT DEFAULT 0.0,
                        min_value FLOAT,
                        max_value FLOAT,
                        unit VARCHAR(20),
                        byte_order VARCHAR(10) DEFAULT 'Motorola',
                        value_type VARCHAR(10) DEFAULT 'Unsigned',
                        cycle_time INTEGER,
                        module VARCHAR(50),
                        description TEXT,
                        source_project_id INTEGER,
                        created_at DATETIME,
                        UNIQUE(signal_id, project_id),
                        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                    )
                """)
                cursor.execute("""
                    INSERT INTO signals_new (
                        id, project_id, name, signal_id, message_name, message_id, dlc,
                        start_bit, bit_length, factor, offset, min_value, max_value, unit,
                        byte_order, value_type, cycle_time, module, description,
                        source_project_id, created_at
                    )
                    SELECT id, COALESCE(project_id, ?), name, signal_id, message_name,
                           message_id, dlc, start_bit, bit_length, factor, offset,
                           min_value, max_value, unit, byte_order, value_type, cycle_time,
                           module, description, source_project_id, created_at
                    FROM signals
                """, (default_pid,))
                cursor.execute("DROP TABLE signals")
                cursor.execute("ALTER TABLE signals_new RENAME TO signals")
            conn.commit()
        except Exception as e:
            print(f"迁移警告: {e}")
            conn.rollback()
            raise


if __name__ == "__main__":
    init_db()
    print(f"数据库已创建: {DB_PATH}")
