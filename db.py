"""
EE-Req Manager — 数据模型与数据库管理
汽车电子电气架构需求管理工具
v0.3: 新增车型管理，支持数据隔离和借用
"""
import os
import json
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime,
    ForeignKey, Float, Boolean, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ee_req.db")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
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


# ========== 系统配置表 ==========
class SysConfig(Base):
    __tablename__ = "sys_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(50), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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
            except:
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

        # 修复旧数据：project_id 为空的设为默认车型
        for table in ["functions", "signals", "func_relations"]:
            cursor.execute(f"UPDATE {table} SET project_id = {default_pid} WHERE project_id IS NULL")
        conn.commit()

        # 删除旧的全局唯一约束，改为 (xxx_id, project_id) 唯一
        # SQLite不支持DROP CONSTRAINT，需要重建表
        _migrate_unique_constraints(conn, cursor, default_pid)

        conn.close()
    finally:
        db.close()


def _migrate_unique_constraints(conn, cursor, default_pid):
    """迁移唯一约束：从全局唯一改为按车型唯一"""
    # 检查 functions 表的索引
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='functions'")
    indexes = cursor.fetchall()

    # 如果 func_id 还是全局唯一，需要重建
    func_cols = [c[1] for c in cursor.execute("PRAGMA table_info(functions)").fetchall()]
    # 检查是否有旧的唯一约束（通过检查索引）
    has_old_unique = False
    for idx_name, idx_sql in indexes:
        if idx_sql and 'func_id' in str(idx_sql) and 'UNIQUE' in str(idx_sql) and 'project_id' not in str(idx_sql):
            has_old_unique = True
            break

    # 对 signals 也做同样检查
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='signals'")
    sig_indexes = cursor.fetchall()
    has_old_sig_unique = False
    for idx_name, idx_sql in sig_indexes:
        if idx_sql and 'signal_id' in str(idx_sql) and 'UNIQUE' in str(idx_sql) and 'project_id' not in str(idx_sql):
            has_old_sig_unique = True
            break

    if has_old_unique or has_old_sig_unique:
        # 需要重建表来修改唯一约束
        # 这个操作比较重，只在旧数据库上执行一次
        try:
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
                        UNIQUE(func_id, project_id)
                    )
                """)
                cursor.execute("INSERT OR IGNORE INTO functions_new SELECT * FROM functions")
                cursor.execute("DROP TABLE functions")
                cursor.execute("ALTER TABLE functions_new RENAME TO functions")
                conn.commit()

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
                        UNIQUE(signal_id, project_id)
                    )
                """)
                cursor.execute("INSERT OR IGNORE INTO signals_new SELECT * FROM signals")
                cursor.execute("DROP TABLE signals")
                cursor.execute("ALTER TABLE signals_new RENAME TO signals")
                conn.commit()
        except Exception as e:
            print(f"迁移警告: {e}")
            conn.rollback()


if __name__ == "__main__":
    init_db()
    print(f"数据库已创建: {DB_PATH}")
