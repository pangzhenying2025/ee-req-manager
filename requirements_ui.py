"""Requirements engineering workspace for EE-Req Manager.

The UI deliberately keeps requirements as the source of truth and treats
functions/signals as downstream architecture artifacts.
"""
from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import streamlit as st
from sqlalchemy.exc import IntegrityError

from collaboration_ui import (
    collaborator_name,
    release_current_lock,
    render_edit_lock,
    verify_edit_lock,
)
from db import (
    Baseline,
    BaselineItem,
    ChangeRecord,
    FuncRelation,
    Function,
    Requirement,
    RequirementModule,
    SessionLocal,
    Signal,
    TraceLink,
    get_config,
)

REQ_TYPES = ["Stakeholder", "Vehicle", "Functional", "System", "Safety", "Interface", "Verification"]
REQ_TYPE_LABELS = {
    "Stakeholder": "利益相关方需求",
    "Vehicle": "整车需求",
    "Functional": "功能需求",
    "System": "系统需求",
    "Safety": "安全需求",
    "Interface": "接口需求",
    "Verification": "验证需求",
}
REQ_LEVELS = ["Stakeholder", "Vehicle", "System", "Subsystem", "Function", "Component", "Interface", "Verification"]
REQ_LEVEL_LABELS = {
    "Stakeholder": "利益相关方层",
    "Vehicle": "整车层",
    "System": "系统层",
    "Subsystem": "子系统层",
    "Function": "功能层",
    "Component": "部件层",
    "Interface": "接口层",
    "Verification": "验证层",
}
REQ_NATURES = ["Functional", "Performance", "Interface", "Safety", "Diagnostic", "Constraint", "Verification"]
REQ_NATURE_LABELS = {
    "Functional": "功能性",
    "Performance": "性能",
    "Interface": "接口",
    "Safety": "安全",
    "Diagnostic": "诊断",
    "Constraint": "约束/非功能",
    "Verification": "验证",
}
LINK_TYPES = ["derives", "decomposes", "satisfies", "allocates", "verifies", "depends", "conflicts"]
LINK_LABELS = {
    "derives": "来源于",
    "decomposes": "分解为",
    "satisfies": "满足",
    "allocates": "分配到",
    "verifies": "验证",
    "depends": "依赖",
    "conflicts": "冲突",
}
STATUS_ORDER = ["Draft", "Review", "Approved", "Released", "Obsolete"]
CHANGE_FIELD_LABELS = {
    "title": "标题",
    "text": "正文",
    "req_type": "类型",
    "req_level": "需求层级",
    "req_nature": "需求性质",
    "status": "状态",
    "priority": "优先级",
    "asil_level": "ASIL",
    "owner": "负责人",
    "source": "来源",
}


def _legacy_requirement_type(req_level: str, req_nature: str) -> str:
    """Keep legacy workflows compatible while dimensions remain independent."""
    if req_nature == "Safety":
        return "Safety"
    if req_nature == "Interface" or req_level == "Interface":
        return "Interface"
    if req_nature == "Verification" or req_level == "Verification":
        return "Verification"
    if req_level == "Stakeholder":
        return "Stakeholder"
    if req_level == "Vehicle":
        return "Vehicle"
    if req_level in ("Subsystem", "Function"):
        return "Functional"
    return "System"


def _automatic_change_reason(changes: list[tuple[str, object, object]]) -> str:
    """Build an auditable reason when the editor leaves the note empty."""
    summaries = []
    for name, old, new in changes:
        old_text = "—" if old in (None, "") else str(old)
        new_text = "—" if new in (None, "") else str(new)
        summaries.append(f"{CHANGE_FIELD_LABELS.get(name, name)}：{old_text} → {new_text}")
    return "系统自动记录：" + "；".join(summaries)


def inject_design_system():
    """Industrial, information-dense styling suitable for engineering work."""
    st.markdown(
        """
        <style>
        :root {
          --ee-ink: #18232b;
          --ee-panel: #f4f1e8;
          --ee-line: #c8c1b3;
          --ee-accent: #e35b2c;
          --ee-cyan: #087e8b;
          color-scheme: only light;
        }
        html, body, [data-testid="stAppViewContainer"] { color-scheme: only light; }
        html, body, [class*="css"] { font-family: "Bahnschrift", "DIN Alternate", sans-serif; }
        .stApp { background:
          linear-gradient(rgba(24,35,43,.025) 1px, transparent 1px),
          linear-gradient(90deg, rgba(24,35,43,.025) 1px, transparent 1px), #f7f5ef;
          background-size: 24px 24px; color:var(--ee-ink); }
        [data-testid="stSidebar"] { background: #18232b; border-right: 4px solid #e35b2c; }
        [data-testid="stSidebar"] * { color: #f4f1e8; }
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
          background:#f7f5ef; border-color:#c8c1b3;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] * {
          color:var(--ee-ink) !important; opacity:1; font-weight:650;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] svg {
          fill:var(--ee-ink) !important;
        }
        [data-testid="stMetric"] {
          background: rgba(255,255,255,.78); border: 1px solid var(--ee-line);
          border-top: 4px solid var(--ee-cyan); padding: 14px 16px;
          box-shadow: 3px 3px 0 rgba(24,35,43,.08); }
        [data-testid="stMetric"] [data-testid="stMetricLabel"],
        [data-testid="stMetric"] [data-testid="stMetricValue"] {
          color:var(--ee-ink) !important; opacity:1 !important; }
        button[data-baseweb="tab"] { color:var(--ee-ink) !important; }
        [data-testid="stAppViewContainer"] label,
        [data-testid="stAppViewContainer"] [data-testid="stWidgetLabel"] p,
        [data-testid="stAppViewContainer"] .stCaption,
        [data-testid="stAppViewContainer"] h1,
        [data-testid="stAppViewContainer"] h2,
        [data-testid="stAppViewContainer"] h3,
        [data-testid="stAppViewContainer"] h4 {
          color:var(--ee-ink) !important; opacity:1 !important; }
        [data-testid="stAppViewContainer"] input,
        [data-testid="stAppViewContainer"] textarea,
        [data-testid="stAppViewContainer"] [data-baseweb="select"] > div {
          background:#eef1f5 !important; color:var(--ee-ink) !important;
          -webkit-text-fill-color:var(--ee-ink) !important; }
        [data-testid="stAppViewContainer"] [data-baseweb="select"] span,
        [data-testid="stAppViewContainer"] input::placeholder,
        [data-testid="stAppViewContainer"] textarea::placeholder {
          color:#52616b !important; opacity:1 !important;
          -webkit-text-fill-color:#52616b !important; }
        .ee-kicker { color: var(--ee-accent); font-size:.76rem; font-weight:700;
          letter-spacing:.16em; text-transform:uppercase; margin-bottom:.25rem; }
        .ee-title { font-size:2.05rem; line-height:1.05; color:var(--ee-ink);
          font-weight:760; letter-spacing:-.035em; margin:0; }
        .ee-subtitle { color:#52616b; max-width:900px; margin:.55rem 0 1.35rem; }
        .ee-strip { border-left:5px solid var(--ee-accent); background:#fff;
          padding:10px 14px; margin:8px 0 18px; box-shadow:2px 2px 0 #d9d2c5; }
        .ee-status { display:inline-block; padding:2px 8px; border-radius:2px;
          background:#dcebed; color:#075f68; font-size:.78rem; font-weight:700; }
        div[data-testid="stDataFrame"] { border:1px solid var(--ee-line); }
        .stButton > button { border-radius:2px; font-weight:700; }
        .stButton > button[kind="primary"] { background:var(--ee-accent); border-color:var(--ee-accent); }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _header(kicker: str, title: str, subtitle: str):
    st.markdown(
        f'<div class="ee-kicker">{kicker}</div><div class="ee-title">{title}</div>'
        f'<div class="ee-subtitle">{subtitle}</div>',
        unsafe_allow_html=True,
    )


def _next_req_id(db, project_id: int, prefix: str = "REQ-") -> str:
    nums = []
    for value, in db.query(Requirement.req_id).filter(Requirement.project_id == project_id).all():
        if value and value.startswith(prefix):
            try:
                nums.append(int(value[len(prefix):]))
            except ValueError:
                continue
    return f"{prefix}{max(nums, default=0) + 1:04d}"


def _artifact_options(db, project_id: int, artifact_type: str):
    if artifact_type == "Requirement":
        rows = db.query(Requirement).filter_by(project_id=project_id).order_by(Requirement.req_id).all()
        return rows, lambda x: f"{x.req_id} · {x.title}"
    if artifact_type == "Function":
        rows = db.query(Function).filter_by(project_id=project_id).order_by(Function.func_id).all()
        return rows, lambda x: f"{x.func_id} · {x.name}"
    rows = db.query(Signal).filter_by(project_id=project_id).order_by(Signal.signal_id).all()
    return rows, lambda x: f"{x.signal_id} · {x.name}"


def _artifact_label(db, project_id: int, artifact_type: str, artifact_id: int) -> str:
    model = {"Requirement": Requirement, "Function": Function, "Signal": Signal}.get(artifact_type)
    if not model:
        return f"{artifact_type}#{artifact_id}"
    obj = db.query(model).filter_by(id=artifact_id, project_id=project_id).first()
    if not obj:
        return f"{artifact_type}#{artifact_id}（已删除）"
    code = getattr(obj, "req_id", None) or getattr(obj, "func_id", None) or getattr(obj, "signal_id", None)
    title = getattr(obj, "title", None) or getattr(obj, "name", "")
    return f"{code} · {title}"


def page_requirements(project_id: int):
    _header("REQUIREMENTS / 需求定义", "需求规范工作台", "用结构化规范承载需求，建立来源、分解、分配和验证链路。")
    db = SessionLocal()
    try:
        modules = db.query(RequirementModule).filter_by(project_id=project_id).order_by(RequirementModule.code).all()
        tab_spec, tab_module, tab_edit = st.tabs(["▤ 规范视图", "＋ 新建规范", "✎ 编辑需求"])

        with tab_spec:
            if not modules:
                st.info("尚无需求规范。请先在“新建规范”中创建第一份规范，例如《整车功能需求规范》。")
            else:
                selected = st.selectbox("当前规范", modules, format_func=lambda m: f"{m.code}  {m.title}")
                reqs = db.query(Requirement).filter_by(project_id=project_id, module_id=selected.id).order_by(
                    Requirement.sort_order, Requirement.req_id
                ).all()
                c1, c2, c3, c4, c5, c6 = st.columns(6)
                c1.metric("需求总数", len(reqs))
                c2.metric("系统层", sum(r.req_level == "System" for r in reqs))
                c3.metric("子系统层", sum(r.req_level == "Subsystem" for r in reqs))
                c4.metric("功能层", sum(r.req_level == "Function" for r in reqs))
                c5.metric("安全性质", sum(r.req_nature == "Safety" for r in reqs))
                c6.metric("版本", f"v{max((r.version for r in reqs), default=0)}")

                f1, f2, f3, f4 = st.columns([1.2, 1.2, 1, 1.2])
                level_filter = f1.multiselect("需求层级", REQ_LEVELS, format_func=lambda x: REQ_LEVEL_LABELS[x])
                nature_filter = f2.multiselect("需求性质", REQ_NATURES, format_func=lambda x: REQ_NATURE_LABELS[x])
                status_filter = f3.multiselect("状态", STATUS_ORDER)
                keyword = f4.text_input("搜索", placeholder="编号 / 标题 / 正文")
                visible = [r for r in reqs if (not level_filter or r.req_level in level_filter)]
                visible = [r for r in visible if (not nature_filter or r.req_nature in nature_filter)]
                visible = [r for r in visible if (not status_filter or r.status in status_filter)]
                if keyword:
                    key = keyword.lower()
                    visible = [r for r in visible if key in f"{r.req_id} {r.title} {r.text}".lower()]

                if visible:
                    parent_codes = {r.id: r.req_id for r in reqs}
                    st.dataframe(pd.DataFrame([{
                        "编号": r.req_id,
                        "标题": r.title,
                        "层级": REQ_LEVEL_LABELS.get(r.req_level, r.req_level or "—"),
                        "性质": REQ_NATURE_LABELS.get(r.req_nature, r.req_nature or "—"),
                        "上级需求": parent_codes.get(r.parent_id, "—"),
                        "状态": r.status,
                        "优先级": r.priority,
                        "ASIL": r.asil_level or "—",
                        "负责人": r.owner or "—",
                        "版本": f"v{r.version}",
                        "更新时间": r.updated_at.strftime("%Y-%m-%d %H:%M") if r.updated_at else "—",
                    } for r in visible]), use_container_width=True, hide_index=True)
                else:
                    st.warning("当前筛选条件下没有需求。")

                with st.expander("＋ 在当前规范中新增需求", expanded=not reqs):
                    with st.form("add_requirement", clear_on_submit=True):
                        a, b, c, d = st.columns([1, 1, 1, 1])
                        req_id = a.text_input("需求编号 *", value=_next_req_id(db, project_id))
                        req_level = b.selectbox("需求层级", REQ_LEVELS, index=2, format_func=lambda x: REQ_LEVEL_LABELS[x])
                        req_nature = c.selectbox("需求性质", REQ_NATURES, format_func=lambda x: REQ_NATURE_LABELS[x])
                        status = d.selectbox("状态", STATUS_ORDER)
                        title = st.text_input("需求标题 *", placeholder="例如：车辆应支持远程闭锁")
                        text = st.text_area("需求正文 *", height=110, placeholder="建议使用‘系统应……，在……条件下……’的可验证句式。")
                        d, e, f = st.columns(3)
                        priority = d.selectbox("优先级", get_config(db, "priority_list", ["High", "Medium", "Low"]), index=1)
                        asil = e.selectbox("ASIL", get_config(db, "asil_list", ["-", "QM", "ASIL-A", "ASIL-B", "ASIL-C", "ASIL-D"]))
                        owner = f.text_input("负责人")
                        parent = st.selectbox("上级需求", [None] + reqs, format_func=lambda x: "— 无 —" if x is None else f"{x.req_id} · {x.title}")
                        source = st.text_input("需求来源", placeholder="法规、客户、上游规范或会议纪要")
                        rationale = st.text_area("设计理由 / 补充说明", height=70)
                        v1, v2 = st.columns(2)
                        verify = v1.selectbox("验证方法", ["", "Test", "Analysis", "Inspection", "Demonstration"])
                        acceptance = v2.text_area("验收准则", height=70)
                        if st.form_submit_button("保存需求", type="primary"):
                            if not req_id.strip() or not title.strip() or not text.strip():
                                st.error("需求编号、标题和正文不能为空。")
                            else:
                                obj = Requirement(
                                    project_id=project_id, module_id=selected.id,
                                    parent_id=parent.id if parent else None,
                                    req_id=req_id.strip(), title=title.strip(), text=text.strip(),
                                    req_type=_legacy_requirement_type(req_level, req_nature),
                                    req_level=req_level, req_nature=req_nature,
                                    status=status, priority=priority,
                                    asil_level=None if asil == "-" else asil, owner=owner.strip() or None,
                                    source=source.strip() or None, rationale=rationale.strip() or None,
                                    verification_method=verify or None,
                                    acceptance_criteria=acceptance.strip() or None,
                                    sort_order=len(reqs) + 1,
                                )
                                db.add(obj)
                                try:
                                    db.commit()
                                    st.success(f"已创建 {obj.req_id}")
                                    st.rerun()
                                except IntegrityError:
                                    db.rollback()
                                    st.error("当前车型中已存在相同需求编号。")

        with tab_module:
            with st.form("add_req_module", clear_on_submit=True):
                st.markdown("#### 新建结构化需求规范")
                c1, c2 = st.columns([1, 2])
                code = c1.text_input("规范编号 *", placeholder="VEH-FRS")
                title = c2.text_input("规范名称 *", placeholder="整车功能需求规范")
                description = st.text_area("适用范围与说明")
                c3, c4 = st.columns(2)
                owner = c3.text_input("负责人")
                status = c4.selectbox("规范状态", STATUS_ORDER)
                if st.form_submit_button("创建规范", type="primary"):
                    if not code.strip() or not title.strip():
                        st.error("规范编号和名称不能为空。")
                    else:
                        db.add(RequirementModule(
                            project_id=project_id, code=code.strip(), title=title.strip(),
                            description=description.strip() or None, owner=owner.strip() or None, status=status,
                        ))
                        try:
                            db.commit()
                            st.success("规范已创建。")
                            st.rerun()
                        except IntegrityError:
                            db.rollback()
                            st.error("当前车型已存在相同规范编号。")

        with tab_edit:
            all_reqs = db.query(Requirement).filter_by(project_id=project_id).order_by(Requirement.req_id).all()
            if not all_reqs:
                st.info("暂无可编辑需求。")
            else:
                requirement_labels = {r.id: f"{r.req_id} · {r.title}" for r in all_reqs}
                selected_requirement_id = st.selectbox(
                    "选择需求",
                    list(requirement_labels),
                    format_func=requirement_labels.get,
                    key="edit_req",
                )
                # Streamlit keeps widget values across reruns. Persisting an ORM
                # instance in the selectbox leaves it detached from this new DB
                # session, so changes appear in the audit log but not on the row.
                selected_req = db.get(Requirement, selected_requirement_id)
                can_edit = render_edit_lock(
                    project_id=project_id,
                    artifact_type="Requirement",
                    artifact_id=selected_req.id,
                    artifact_label=f"{selected_req.req_id} · {selected_req.title}",
                )
                with st.form("edit_requirement"):
                    e1, e2, e3, e4 = st.columns([1.4, 1, 1, 1])
                    title = e1.text_input("标题", value=selected_req.title)
                    current_level = selected_req.req_level if selected_req.req_level in REQ_LEVELS else "System"
                    current_nature = selected_req.req_nature if selected_req.req_nature in REQ_NATURES else "Functional"
                    req_level = e2.selectbox("需求层级", REQ_LEVELS, index=REQ_LEVELS.index(current_level), format_func=lambda x: REQ_LEVEL_LABELS[x])
                    req_nature = e3.selectbox("需求性质", REQ_NATURES, index=REQ_NATURES.index(current_nature), format_func=lambda x: REQ_NATURE_LABELS[x])
                    status = e4.selectbox("状态", STATUS_ORDER, index=STATUS_ORDER.index(selected_req.status) if selected_req.status in STATUS_ORDER else 0)
                    text = st.text_area("正文", value=selected_req.text, height=130)
                    e4, e5, e6 = st.columns(3)
                    priority_opts = get_config(db, "priority_list", ["High", "Medium", "Low"])
                    priority = e4.selectbox("优先级", priority_opts, index=priority_opts.index(selected_req.priority) if selected_req.priority in priority_opts else 1)
                    asil_opts = get_config(db, "asil_list", ["-", "QM", "ASIL-A", "ASIL-B", "ASIL-C", "ASIL-D"])
                    old_asil = selected_req.asil_level or "-"
                    asil = e5.selectbox("ASIL", asil_opts, index=asil_opts.index(old_asil) if old_asil in asil_opts else 0)
                    owner = e6.text_input("负责人", value=selected_req.owner or "")
                    source = st.text_input("来源", value=selected_req.source or "")
                    reason = st.text_area(
                        "本次变更说明（可选）",
                        placeholder="可填写修改原因；留空时系统会按变更字段自动生成审计记录。",
                    )
                    save_requirement = st.form_submit_button(
                        "保存新版本",
                        type="primary",
                        disabled=not can_edit,
                    )
                    if save_requirement:
                        if not verify_edit_lock(project_id, "Requirement", selected_req.id):
                            st.error("编辑权已失效或已被其他成员取得，本次内容未保存。")
                        elif not title.strip() or not text.strip():
                            st.error("标题和正文不能为空。")
                        else:
                            fields = {
                                "title": title.strip(), "text": text.strip(),
                                "req_type": _legacy_requirement_type(req_level, req_nature),
                                "req_level": req_level, "req_nature": req_nature,
                                "status": status, "priority": priority,
                                "asil_level": None if asil == "-" else asil,
                                "owner": owner.strip() or None, "source": source.strip() or None,
                            }
                            changes = [(name, getattr(selected_req, name), value) for name, value in fields.items() if getattr(selected_req, name) != value]
                            if not changes:
                                st.info("没有检测到内容变化。")
                            else:
                                audit_reason = reason.strip() or _automatic_change_reason(changes)
                                for name, old, new in changes:
                                    db.add(ChangeRecord(
                                        project_id=project_id, requirement_id=selected_req.id,
                                        change_type="Update", field_name=name,
                                        old_value="" if old is None else str(old),
                                        new_value="" if new is None else str(new), reason=audit_reason,
                                        changed_by=collaborator_name(),
                                    ))
                                    setattr(selected_req, name, new)
                                selected_req.version += 1
                                selected_req.updated_at = datetime.utcnow()
                                db.commit()
                                release_current_lock(project_id, "Requirement", selected_req.id)
                                st.success(f"{selected_req.req_id} 已更新至 v{selected_req.version}")
                                st.rerun()

                with st.expander("危险操作"):
                    st.warning("删除需求会同时删除其变更记录；指向该需求的追溯链接也会被清理。")
                    confirm = st.checkbox(f"确认删除 {selected_req.req_id}", key="confirm_delete_req")
                    if st.button("删除需求", disabled=not (confirm and can_edit)):
                        if not verify_edit_lock(project_id, "Requirement", selected_req.id):
                            st.error("编辑权已失效，本次删除未执行。")
                        else:
                            db.query(TraceLink).filter_by(project_id=project_id, source_type="Requirement", source_id=selected_req.id).delete()
                            db.query(TraceLink).filter_by(project_id=project_id, target_type="Requirement", target_id=selected_req.id).delete()
                            db.delete(selected_req)
                            db.commit()
                            release_current_lock(project_id, "Requirement", selected_req.id)
                            st.rerun()
    finally:
        db.close()


def _build_function_requirement_trace(functions, relations, requirements, signals, links):
    """Build a project-scoped function → requirement → signal/test trace tree."""
    function_by_id = {item.id: item for item in functions}
    requirement_by_id = {item.id: item for item in requirements}
    signal_by_id = {item.id: item for item in signals}
    function_children = {}
    for relation in relations:
        if (
            relation.rel_type in ("分解", "decomposes")
            and relation.source_id in function_by_id
            and relation.target_id in function_by_id
        ):
            function_children.setdefault(relation.source_id, []).append(relation.target_id)

    requirements_by_function = {}
    outgoing_by_requirement = {}
    incoming_by_requirement = {}
    for link in links:
        if link.source_type == "Requirement":
            outgoing_by_requirement.setdefault(link.source_id, []).append(link)
        if link.target_type == "Requirement":
            incoming_by_requirement.setdefault(link.target_id, []).append(link)
        if (
            link.source_type == "Requirement"
            and link.target_type == "Function"
            and link.source_id in requirement_by_id
            and link.target_id in function_by_id
            and link.link_type == "allocates"
        ):
            requirements_by_function.setdefault(link.target_id, []).append(requirement_by_id[link.source_id])

    requirement_children = {}
    for requirement in requirements:
        if requirement.parent_id in requirement_by_id:
            requirement_children.setdefault(requirement.parent_id, []).append(requirement)

    def labels(items, id_field, title_field):
        unique = {getattr(item, id_field): item for item in items}
        return [
            {
                "id": getattr(item, id_field),
                "title": getattr(item, title_field),
                "label": f"{getattr(item, id_field)} · {getattr(item, title_field)}",
            }
            for item in sorted(unique.values(), key=lambda value: str(getattr(value, id_field)))
        ]

    def requirement_bundle(allocated):
        allocated = list({item.id: item for item in allocated}.values())
        interfaces = []
        verifications = []
        for requirement in allocated:
            for child in requirement_children.get(requirement.id, []):
                if child.req_type == "Interface":
                    interfaces.append(child)
                elif child.req_type == "Verification":
                    verifications.append(child)
            connected = outgoing_by_requirement.get(requirement.id, []) + incoming_by_requirement.get(requirement.id, [])
            for link in connected:
                if link.link_type != "verifies":
                    continue
                other_id = link.target_id if link.source_id == requirement.id else link.source_id
                other = requirement_by_id.get(other_id)
                if other is not None and other.req_type == "Verification":
                    verifications.append(other)

        signal_rows = []
        for requirement in [*allocated, *interfaces]:
            for link in outgoing_by_requirement.get(requirement.id, []):
                if link.target_type == "Signal" and link.link_type == "allocates":
                    signal = signal_by_id.get(link.target_id)
                    if signal is not None:
                        signal_rows.append(signal)
        return {
            "requirements": labels(allocated, "req_id", "title"),
            "interfaces": labels(interfaces, "req_id", "title"),
            "signals": labels(signal_rows, "signal_id", "name"),
            "verifications": labels(verifications, "req_id", "title"),
        }

    def function_node(function):
        return {
            "function_id": function.func_id,
            "name": function.name,
            "module": function.module or "待确认",
            "category": function.category or "—",
            **requirement_bundle(requirements_by_function.get(function.id, [])),
        }

    subsystems = []
    atomic_rows = []
    subsystem_functions = sorted(
        (item for item in functions if str(item.func_id).startswith("SL")),
        key=lambda item: item.func_id,
    )
    for subsystem in subsystem_functions:
        subsystem_node = function_node(subsystem)
        subsystem_node["logicals"] = []
        logical_functions = [
            function_by_id[item_id]
            for item_id in function_children.get(subsystem.id, [])
            if str(function_by_id[item_id].func_id).startswith("LC")
        ]
        for logical in sorted(logical_functions, key=lambda item: item.func_id):
            logical_node = function_node(logical)
            logical_node["atomics"] = []
            atomic_functions = [
                function_by_id[item_id]
                for item_id in function_children.get(logical.id, [])
                if str(function_by_id[item_id].func_id).startswith("AF")
            ]
            for atomic in sorted(atomic_functions, key=lambda item: item.func_id):
                atomic_node = function_node(atomic)
                logical_node["atomics"].append(atomic_node)
                atomic_rows.append(atomic_node)
            subsystem_node["logicals"].append(logical_node)
        subsystems.append(subsystem_node)

    summary = {
        "subsystems": len(subsystems),
        "logicals": sum(len(item["logicals"]) for item in subsystems),
        "atomics": len(atomic_rows),
        "requirements_covered": sum(bool(item["requirements"]) for item in atomic_rows),
        "signals_covered": sum(bool(item["signals"]) for item in atomic_rows),
        "verification_covered": sum(bool(item["verifications"]) for item in atomic_rows),
    }
    return {"summary": summary, "subsystems": subsystems}


def _render_function_requirement_tree(tree, project_id: int):
    st.caption("功能架构与需求对象保持独立，通过分配和分解链路形成：系统（SL）→ 子系统（LC）→ 具体功能（AF）→ 需求 → 接口/信号 → 验证。")
    subsystems = tree["subsystems"]
    if not subsystems:
        st.info("当前车型尚未建立系统（SL）、子系统（LC）和具体功能（AF）层级。")
        return

    subsystem_labels = {
        item["function_id"]: f"{item['function_id']} · {item['name']}"
        for item in subsystems
    }
    selected_subsystem_id = st.selectbox(
        "选择系统（SL）",
        list(subsystem_labels),
        format_func=subsystem_labels.get,
        key=f"trace_tree_subsystem_{project_id}",
    )
    selected_subsystem = next(item for item in subsystems if item["function_id"] == selected_subsystem_id)
    logical_labels = {"全部": "全部子系统"} | {
        item["function_id"]: f"{item['function_id']} · {item['name']}"
        for item in selected_subsystem["logicals"]
    }
    c_filter, c_gap = st.columns([2, 1])
    selected_logical_id = c_filter.selectbox(
        "筛选子系统（LC）",
        list(logical_labels),
        format_func=logical_labels.get,
        key=f"trace_tree_logical_{project_id}_{selected_subsystem_id}",
    )
    only_gaps = c_gap.checkbox(
        "仅显示追溯缺口",
        key=f"trace_tree_gaps_{project_id}_{selected_subsystem_id}",
    )

    atomics = [
        atomic
        for logical in selected_subsystem["logicals"]
        if selected_logical_id == "全部" or logical["function_id"] == selected_logical_id
        for atomic in logical["atomics"]
    ]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("具体功能", len(atomics))
    c2.metric("需求覆盖", f"{sum(bool(item['requirements']) for item in atomics)}/{len(atomics)}")
    c3.metric("信号覆盖", f"{sum(bool(item['signals']) for item in atomics)}/{len(atomics)}")
    c4.metric("验证覆盖", f"{sum(bool(item['verifications']) for item in atomics)}/{len(atomics)}")

    st.markdown(f"### {selected_subsystem['function_id']} · {selected_subsystem['name']}")
    st.caption(
        f"责任节点：{selected_subsystem['module']}　|　"
        f"分配需求：{len(selected_subsystem['requirements'])}　|　"
        f"子系统：{len(selected_subsystem['logicals'])}"
    )
    visible_rows = []
    for logical in selected_subsystem["logicals"]:
        if selected_logical_id != "全部" and logical["function_id"] != selected_logical_id:
            continue
        logical_atomics = [
            item for item in logical["atomics"]
            if not only_gaps or not (item["requirements"] and item["signals"] and item["verifications"])
        ]
        if only_gaps and not logical_atomics:
            continue
        req_text = "、".join(item["label"] for item in logical["requirements"]) or "未分配需求"
        with st.expander(
            f"{logical['function_id']} · {logical['name']}　|　具体功能 {len(logical['atomics'])}　|　需求 {len(logical['requirements'])}",
            expanded=logical["function_id"] == "LC01-01",
        ):
            st.markdown(f"**子系统层需求：** {req_text}")
            st.caption(f"责任节点：{logical['module']}　|　功能域：{logical['category']}")
            for atomic in logical_atomics:
                req_ok = bool(atomic["requirements"])
                signal_ok = bool(atomic["signals"])
                verification_ok = bool(atomic["verifications"])
                status = f"需求{'✓' if req_ok else '✗'}　信号{'✓' if signal_ok else '✗'}　验证{'✓' if verification_ok else '✗'}"
                with st.container(border=True):
                    st.markdown(f"#### {atomic['function_id']} · {atomic['name']}")
                    st.caption(f"责任节点：{atomic['module']}　|　{status}")
                    left, right = st.columns(2)
                    left.markdown("**系统需求**")
                    left.markdown("\n\n".join(f"- {item['label']}" for item in atomic["requirements"]) or "- ⚠️ 未分配")
                    left.markdown("**验证需求**")
                    left.markdown("\n\n".join(f"- {item['label']}" for item in atomic["verifications"]) or "- ⚠️ 未覆盖")
                    right.markdown("**接口需求**")
                    right.markdown("\n\n".join(f"- {item['label']}" for item in atomic["interfaces"]) or "- ⚠️ 未建立关联")
                    right.markdown("**DBC信号**")
                    right.markdown("\n\n".join(f"- {item['label']}" for item in atomic["signals"]) or "- ⚠️ 未建立关联")
                visible_rows.append({
                    "系统（SL）": selected_subsystem["function_id"],
                    "子系统（LC）": logical["function_id"],
                    "具体功能（AF）": f"{atomic['function_id']} · {atomic['name']}",
                    "责任节点": atomic["module"],
                    "系统需求": len(atomic["requirements"]),
                    "接口需求": len(atomic["interfaces"]),
                    "DBC信号": len(atomic["signals"]),
                    "验证需求": len(atomic["verifications"]),
                    "完整性": "通过" if req_ok and signal_ok and verification_ok else "存在缺口",
                })
    if visible_rows:
        st.markdown("#### 当前视图追溯矩阵")
        st.dataframe(pd.DataFrame(visible_rows), use_container_width=True, hide_index=True)
    elif only_gaps:
        st.success("当前筛选范围内没有追溯缺口。")


def page_traceability(project_id: int):
    _header("TRACEABILITY / 架构追溯", "追溯与分配工作台", "把需求连接到上游需求、逻辑功能和接口信号，并自动识别断链。")
    db = SessionLocal()
    try:
        requirements = db.query(Requirement).filter_by(project_id=project_id).order_by(Requirement.req_id).all()
        links = db.query(TraceLink).filter_by(project_id=project_id).order_by(TraceLink.id.desc()).all()
        if not requirements:
            st.info("请先在需求规范工作台创建需求。")
            return

        tab_tree, tab_map, tab_create, tab_matrix = st.tabs(["🌳 功能—需求树", "⌁ 链路清单", "＋ 建立追溯", "▦ 覆盖分析"])
        with tab_tree:
            functions = db.query(Function).filter_by(project_id=project_id).order_by(Function.func_id).all()
            relations = db.query(FuncRelation).filter_by(project_id=project_id).all()
            signals = db.query(Signal).filter_by(project_id=project_id).all()
            tree = _build_function_requirement_trace(functions, relations, requirements, signals, links)
            _render_function_requirement_tree(tree, project_id)

        with tab_map:
            if not links:
                st.info("尚未建立追溯关系。")
            else:
                st.dataframe(pd.DataFrame([{
                    "来源": _artifact_label(db, project_id, link.source_type, link.source_id),
                    "关系": LINK_LABELS.get(link.link_type, link.link_type),
                    "目标": _artifact_label(db, project_id, link.target_type, link.target_id),
                    "说明": link.description or "—",
                    "创建时间": link.created_at.strftime("%Y-%m-%d %H:%M") if link.created_at else "—",
                } for link in links]), use_container_width=True, hide_index=True)
                link_labels = {
                    link.id: f"#{link.id} {_artifact_label(db, project_id, link.source_type, link.source_id)} → "
                    f"{_artifact_label(db, project_id, link.target_type, link.target_id)}"
                    for link in links
                }
                with st.expander("编辑追溯关系"):
                    edit_link_id = st.selectbox(
                        "选择要编辑的链路", list(link_labels), format_func=link_labels.get,
                        key="edit_trace_link_id",
                    )
                    edit_link = db.get(TraceLink, edit_link_id)
                    artifact_types = ["Requirement", "Function", "Signal"]
                    artifact_type_labels = {"Requirement": "需求", "Function": "功能", "Signal": "信号"}

                    es1, es2 = st.columns(2)
                    edit_source_type = es1.selectbox(
                        "来源对象类型", artifact_types,
                        index=artifact_types.index(edit_link.source_type),
                        format_func=artifact_type_labels.get,
                        key=f"edit_source_type_{edit_link_id}",
                    )
                    edit_link_type = es2.selectbox(
                        "关系类型", LINK_TYPES,
                        index=LINK_TYPES.index(edit_link.link_type) if edit_link.link_type in LINK_TYPES else 0,
                        format_func=lambda value: LINK_LABELS[value],
                        key=f"edit_link_type_{edit_link_id}",
                    )
                    edit_source_rows, edit_source_fmt = _artifact_options(db, project_id, edit_source_type)
                    edit_source_labels = {row.id: edit_source_fmt(row) for row in edit_source_rows}
                    source_default = edit_link.source_id if edit_link.source_type == edit_source_type else None
                    source_ids = list(edit_source_labels)
                    edit_source_id = st.selectbox(
                        "来源对象", source_ids,
                        index=source_ids.index(source_default) if source_default in source_ids else 0,
                        format_func=edit_source_labels.get,
                        key=f"edit_source_{edit_link_id}_{edit_source_type}",
                    ) if source_ids else None

                    edit_target_type = st.selectbox(
                        "目标对象类型", artifact_types,
                        index=artifact_types.index(edit_link.target_type),
                        format_func=artifact_type_labels.get,
                        key=f"edit_target_type_{edit_link_id}",
                    )
                    edit_target_rows, edit_target_fmt = _artifact_options(db, project_id, edit_target_type)
                    edit_target_labels = {row.id: edit_target_fmt(row) for row in edit_target_rows}
                    target_default = edit_link.target_id if edit_link.target_type == edit_target_type else None
                    target_ids = list(edit_target_labels)
                    edit_target_id = st.selectbox(
                        "目标对象", target_ids,
                        index=target_ids.index(target_default) if target_default in target_ids else 0,
                        format_func=edit_target_labels.get,
                        key=f"edit_target_{edit_link_id}_{edit_target_type}",
                    ) if target_ids else None
                    edit_description = st.text_area(
                        "关系说明", value=edit_link.description or "",
                        key=f"edit_description_{edit_link_id}",
                    )
                    if st.button(
                        "保存链路修改", type="primary",
                        disabled=edit_source_id is None or edit_target_id is None,
                    ):
                        if edit_source_type == edit_target_type and edit_source_id == edit_target_id:
                            st.error("不能把对象链接到自身。")
                        else:
                            edit_link.source_type = edit_source_type
                            edit_link.source_id = edit_source_id
                            edit_link.link_type = edit_link_type
                            edit_link.target_type = edit_target_type
                            edit_link.target_id = edit_target_id
                            edit_link.description = edit_description.strip() or None
                            try:
                                db.commit()
                                st.success("追溯关系已更新。")
                                st.rerun()
                            except IntegrityError:
                                db.rollback()
                                st.warning("修改后的追溯关系已经存在。")

                with st.expander("删除追溯关系"):
                    selected_link_id = st.selectbox(
                        "选择链路", list(link_labels), format_func=link_labels.get,
                    )
                    if st.button("删除所选链路"):
                        selected_link = db.get(TraceLink, selected_link_id)
                        if selected_link is not None and selected_link.project_id == project_id:
                            db.delete(selected_link)
                        db.commit()
                        st.rerun()

        with tab_create:
            # Dependent dropdowns must rerun immediately when the artifact type
            # changes. A Streamlit form delays all widget updates until submit,
            # which previously left a Function selected after choosing Signal.
            with st.container(border=True):
                source_type = st.selectbox("来源对象类型", ["Requirement", "Function", "Signal"], format_func=lambda x: {"Requirement": "需求", "Function": "功能", "Signal": "信号"}[x])
                source_rows, source_fmt = _artifact_options(db, project_id, source_type)
                source_labels = {row.id: source_fmt(row) for row in source_rows}
                source_id = st.selectbox(
                    "来源对象", list(source_labels), format_func=source_labels.get,
                    key=f"trace_source_{project_id}_{source_type}",
                ) if source_rows else None
                c1, c2 = st.columns(2)
                link_type = c1.selectbox("关系类型", LINK_TYPES, format_func=lambda x: LINK_LABELS[x])
                target_type = c2.selectbox("目标对象类型", ["Requirement", "Function", "Signal"], index=1, format_func=lambda x: {"Requirement": "需求", "Function": "功能", "Signal": "信号"}[x])
                target_rows, target_fmt = _artifact_options(db, project_id, target_type)
                target_labels = {row.id: target_fmt(row) for row in target_rows}
                target_id = st.selectbox(
                    "目标对象", list(target_labels), format_func=target_labels.get,
                    key=f"trace_target_{project_id}_{target_type}",
                ) if target_rows else None
                description = st.text_area("关系说明")
                if st.button("建立双向可追溯链路", type="primary"):
                    if source_id is None or target_id is None:
                        st.error("来源对象和目标对象不能为空。")
                    elif source_type == target_type and source_id == target_id:
                        st.error("不能把对象链接到自身。")
                    else:
                        db.add(TraceLink(
                            project_id=project_id, source_type=source_type, source_id=source_id,
                            target_type=target_type, target_id=target_id, link_type=link_type,
                            description=description.strip() or None,
                            created_by=collaborator_name(),
                        ))
                        try:
                            db.commit()
                            st.success("追溯关系已建立。")
                            st.rerun()
                        except IntegrityError:
                            db.rollback()
                            st.warning("该追溯关系已经存在。")

        with tab_matrix:
            outgoing = {}
            incoming = {}
            for link in links:
                if link.source_type == "Requirement":
                    outgoing.setdefault(link.source_id, []).append(link)
                if link.target_type == "Requirement":
                    incoming.setdefault(link.target_id, []).append(link)
            rows = []
            for req in requirements:
                outs = outgoing.get(req.id, [])
                ins = incoming.get(req.id, [])
                architecture = [link for link in outs if link.target_type in ("Function", "Signal")]
                verified = any(link.link_type == "verifies" for link in outs + ins)
                issues = []
                if req.req_level not in ("Stakeholder", "Vehicle") and not ins:
                    issues.append("缺少上游来源")
                if req.req_nature in ("Functional", "Safety", "Interface") and not architecture:
                    issues.append("未分配架构对象")
                if req.status in ("Approved", "Released") and not verified:
                    issues.append("缺少验证链路")
                rows.append({
                    "需求": f"{req.req_id} · {req.title}",
                    "层级": REQ_LEVEL_LABELS.get(req.req_level, req.req_level or "—"),
                    "性质": REQ_NATURE_LABELS.get(req.req_nature, req.req_nature or "—"),
                    "上游链路": len(ins), "下游链路": len(outs),
                    "架构分配": len(architecture), "验证": "已覆盖" if verified else "未覆盖",
                    "完整性": "通过" if not issues else "；".join(issues),
                })
            healthy = sum(r["完整性"] == "通过" for r in rows)
            c1, c2, c3 = st.columns(3)
            c1.metric("需求总数", len(rows))
            c2.metric("完整需求", healthy)
            c3.metric("追溯完整率", f"{healthy / len(rows):.0%}" if rows else "0%")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.caption("规则：非顶层需求需要上游来源；功能/系统/安全/接口需求需要分配到功能或信号；已批准需求需要验证链路。")
    finally:
        db.close()


def _snapshot(model_obj, fields):
    return {field: getattr(model_obj, field) for field in fields}


def page_baselines(project_id: int):
    _header("CONFIGURATION / 配置管理", "基线与变更审计", "冻结车型某一时点的需求和架构状态，支持版本审计与差异识别。")
    db = SessionLocal()
    try:
        baselines = db.query(Baseline).filter_by(project_id=project_id).order_by(Baseline.created_at.desc()).all()
        tab_base, tab_changes = st.tabs(["◆ 版本基线", "↺ 变更历史"])
        with tab_base:
            with st.form("create_baseline"):
                st.markdown("#### 创建不可变快照")
                c1, c2 = st.columns(2)
                name = c1.text_input("基线名称 *", placeholder="SOP-GATE-01")
                creator = c2.text_input("创建人")
                description = st.text_area("基线说明", placeholder="例如：整车功能定义评审通过版本")
                if st.form_submit_button("冻结当前配置", type="primary"):
                    if not name.strip():
                        st.error("基线名称不能为空。")
                    else:
                        baseline = Baseline(project_id=project_id, name=name.strip(), description=description.strip() or None, created_by=creator.strip() or None)
                        db.add(baseline)
                        try:
                            db.flush()
                            specs = [
                                ("Requirement", Requirement, ["req_id", "title", "text", "req_type", "req_level", "req_nature", "status", "priority", "asil_level", "owner", "version"]),
                                ("Function", Function, ["func_id", "name", "category", "module", "description", "status", "asil_level"]),
                                ("Signal", Signal, ["signal_id", "name", "message_name", "message_id", "module", "description"]),
                                ("TraceLink", TraceLink, ["source_type", "source_id", "target_type", "target_id", "link_type", "description"]),
                            ]
                            for artifact_type, model, fields in specs:
                                for obj in db.query(model).filter_by(project_id=project_id).all():
                                    db.add(BaselineItem(
                                        baseline_id=baseline.id, artifact_type=artifact_type,
                                        artifact_id=obj.id,
                                        snapshot=json.dumps(_snapshot(obj, fields), ensure_ascii=False, default=str),
                                    ))
                            db.commit()
                            st.success(f"基线 {baseline.name} 已冻结。")
                            st.rerun()
                        except IntegrityError:
                            db.rollback()
                            st.error("当前车型已存在相同基线名称。")

            if baselines:
                st.markdown("#### 已冻结基线")
                st.dataframe(pd.DataFrame([{
                    "基线": b.name, "说明": b.description or "—", "创建人": b.created_by or "—",
                    "对象数": len(b.items), "创建时间": b.created_at.strftime("%Y-%m-%d %H:%M"),
                } for b in baselines]), use_container_width=True, hide_index=True)
                selected = st.selectbox("查看基线内容", baselines, format_func=lambda b: f"{b.name} · {b.created_at:%Y-%m-%d %H:%M}")
                type_filter = st.selectbox("对象类型", ["Requirement", "Function", "Signal", "TraceLink"])
                items = [item for item in selected.items if item.artifact_type == type_filter]
                if items:
                    st.dataframe(pd.DataFrame([json.loads(item.snapshot) for item in items]), use_container_width=True, hide_index=True)
                else:
                    st.info("该基线中没有此类对象。")
            else:
                st.info("尚未创建基线。建议在需求评审、架构冻结和项目里程碑时创建。")

        with tab_changes:
            records = db.query(ChangeRecord).filter_by(project_id=project_id).order_by(ChangeRecord.changed_at.desc()).all()
            if not records:
                st.info("尚无需求变更记录。通过“编辑需求”保存新版本后会自动记录。")
            else:
                req_map = {r.id: r.req_id for r in db.query(Requirement).filter_by(project_id=project_id).all()}
                st.dataframe(pd.DataFrame([{
                    "需求": req_map.get(c.requirement_id, f"#{c.requirement_id}"),
                    "变更字段": c.field_name or c.change_type,
                    "原值": c.old_value or "—", "新值": c.new_value or "—",
                    "原因": c.reason or "—", "变更人": c.changed_by or "—",
                    "时间": c.changed_at.strftime("%Y-%m-%d %H:%M"),
                } for c in records]), use_container_width=True, hide_index=True)
    finally:
        db.close()
