"""Small, deterministic automotive scenario for development and UI regression."""

import json

from db import (
    FuncRelation,
    Function,
    FunctionSignal,
    Project,
    Requirement,
    RequirementModule,
    Signal,
    SysConfig,
    TraceLink,
)
from services.signal_endpoints import sync_signal_endpoints

DEMO_PROJECT = "开发演示车"
DEMO_CODE = "DEV-DEMO"


def seed_demo(session):
    """Create one complete trace chain once; leave existing demo edits intact."""
    existing = session.query(Project).filter_by(code=DEMO_CODE).first()
    if existing:
        return existing.id
    project = Project(name=DEMO_PROJECT, code=DEMO_CODE, description="自动生成的开发演示数据")
    session.add(project)
    session.flush()
    pid = project.id
    functions = [
        Function(project_id=pid, func_id="SL01", name="车身控制系统", module="BCM", category="车身"),
        Function(project_id=pid, func_id="LC01-01", name="车门闭锁子系统", module="BCM", category="车身"),
        Function(project_id=pid, func_id="AF-001", name="远程闭锁", module="BCM", category="车身"),
    ]
    session.add_all(functions)
    session.flush()
    for parent, child in zip(functions, functions[1:]):
        session.add(FuncRelation(project_id=pid, source_id=parent.id, target_id=child.id, rel_type="分解"))

    module = RequirementModule(project_id=pid, code="DEMO-SYS", title="车身控制需求规范", owner="开发工程师")
    session.add(module)
    session.flush()
    requirement = Requirement(
        project_id=pid, module_id=module.id, req_id="SYS-DEMO-001", title="远程闭锁响应",
        text="在四门关闭且车辆处于驻车状态时，BCM 应在收到有效远程闭锁请求后 200 ms 内锁止车门。",
        req_type="System", req_level="System", req_nature="Functional", owner="BCM",
        source="开发演示场景", verification_method="Test",
        acceptance_criteria="发送有效闭锁请求，200 ms 内门锁反馈为 Locked。",
    )
    session.add(requirement)
    session.flush()
    interface = Requirement(
        project_id=pid, module_id=module.id, parent_id=requirement.id,
        req_id="IF-DEMO-001", title="车门锁状态接口", req_type="Interface",
        req_level="Interface", req_nature="Interface",
        text="BCM 应通过 DoorLockStatus 信号发送门锁状态，发送周期为 100 ms。",
    )
    verification = Requirement(
        project_id=pid, module_id=module.id, parent_id=requirement.id,
        req_id="VER-DEMO-001", title="闭锁响应验证", req_type="Verification",
        req_level="Verification", req_nature="Verification",
        text="测试应测量有效闭锁请求到锁止反馈的时间，判定其不超过 200 ms。",
    )
    session.add_all([interface, verification])
    signals = []
    for index, (name, receivers) in enumerate([
        ("DoorLockStatus", "ICM, GW"), ("DoorAjarStatus", "ICM"), ("VehicleSpeed", "BCM, GW"),
        ("LockRequest", "BCM"), ("RemoteLockCounter", "ICM"),
    ]):
        signal = Signal(
            project_id=pid, signal_id=f"DEMO-SIG-{index + 1:03}", name=name,
            message_name="BCM_DoorStatus", message_id="0x301", dlc=8,
            start_bit=index * 8, bit_length=8, factor=1.0, offset=0.0,
            min_value=0.0, max_value=255.0, byte_order="Intel", value_type="Unsigned",
            cycle_time=100, module="BCM", unit="km/h" if name == "VehicleSpeed" else "",
            description=f"开发演示接口\n总线: DEMOCAN\n发送节点: BCM\n接收节点: {receivers}\n来源: demo.dbc",
        )
        session.add(signal)
        signals.append(signal)
    session.flush()
    session.add(FunctionSignal(function_id=functions[-1].id, signal_id=signals[0].id, direction="Output"))
    for source, target_type, target, kind in [
        (requirement, "Function", functions[-1], "allocates"),
        (interface, "Signal", signals[0], "allocates"),
        (verification, "Requirement", requirement, "verifies"),
    ]:
        session.add(TraceLink(
            project_id=pid, source_type="Requirement", source_id=source.id,
            target_type=target_type, target_id=target.id, link_type=kind,
        ))
    config = session.query(SysConfig).filter_by(key="ecu_list").first()
    ecus = ["BCM", "ICM", "GW", "ADAS", "VCU"]
    if config:
        config.value = json.dumps(sorted(set(json.loads(config.value)) | set(ecus)), ensure_ascii=False)
    else:
        session.add(SysConfig(key="ecu_list", value=json.dumps(ecus)))
    session.commit()
    sync_signal_endpoints(session, pid)
    return pid
