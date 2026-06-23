"""
EE-Req Manager — 汽车电子电气架构需求管理工具
Streamlit 主应用
"""
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
from datetime import datetime
from sqlalchemy import func as sql_func
import cantools
import openpyxl
import tempfile
import os
from db import init_db, SessionLocal, Function, Signal, FunctionSignal, FuncRelation, SignalFuncRelation, SysConfig, Project, get_config, set_config, ensure_default_project
from i18n import t, tpl, lang_selector

# ========== 初始化 ==========
init_db()

st.set_page_config(
    page_title="EE-Req Manager",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== 侧边栏 ==========
st.sidebar.title("🚗 EE-Req Manager")
st.sidebar.caption(t("汽车电子电气架构需求管理"))
st.sidebar.divider()

# ========== 车型选择器 ==========
db_sidebar = SessionLocal()
try:
    projects = db_sidebar.query(Project).order_by(Project.id).all()
    project_names = [p.name for p in projects]
    if not project_names:
        ensure_default_project(db_sidebar)
        projects = db_sidebar.query(Project).order_by(Project.id).all()
        project_names = [p.name for p in projects]
finally:
    db_sidebar.close()

sel_project = st.sidebar.selectbox(t("🚘 当前车型"), project_names, key="sel_project")
# 获取当前车型ID
db_proj = SessionLocal()
try:
    current_project = db_proj.query(Project).filter_by(name=sel_project).first()
    current_project_id = current_project.id if current_project else 1
finally:
    db_proj.close()

st.sidebar.divider()

lang_selector()
st.sidebar.divider()

# 导航列表（显示标签可翻译，路由key保持中文）
NAV_KEYS = ["📊 总览仪表盘", "📋 功能管理", "📡 信号管理", "📥 DBC导入",
            "📥 Excel通讯矩阵", "🔗 功能-信号关联", "🔄 逻辑关系",
            "📊 追溯矩阵", "📤 数据导出", "🚘 车型管理", "⚙️ 配置管理"]
NAV_LABELS = [t(k) for k in NAV_KEYS]
page_label = st.sidebar.radio(
    t("导航"),
    NAV_LABELS,
    label_visibility="collapsed"
)
page = NAV_KEYS[NAV_LABELS.index(page_label)]
st.sidebar.divider()
st.sidebar.caption(f"v0.3.0 | {datetime.now().strftime('%Y-%m-%d')}")


# ========== 通用工具 ==========
def get_session():
    return SessionLocal()


def safe_num(v, cast, default):
    """安全转换数字，转换失败返回默认值"""
    try:
        return cast(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def safe_decode(text):
    """修复DBC中文乱码：Latin-1误读 → GBK还原"""
    try:
        text.encode('ascii')
        return text
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    try:
        return text.encode('latin-1').decode('gbk')
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def notify(msg, ntype="success"):
    """通用通知：存到session_state，rerun后显示"""
    st.session_state._notify = {"type": ntype, "msg": msg}


def render_notify():
    """渲染通知：在各页面顶部调用"""
    if "_notify" in st.session_state:
        n = st.session_state._notify
        if n["type"] == "success":
            st.success(n["msg"])
        elif n["type"] == "error":
            st.error(n["msg"])
        elif n["type"] == "warning":
            st.warning(n["msg"])
        elif n["type"] == "info":
            st.info(n["msg"])
        del st.session_state._notify


def next_id(prefix, model, id_field="func_id"):
    """生成下一个编号 如 FUNC-001"""
    db = get_session()
    try:
        items = db.query(model).all()
        nums = []
        for item in items:
            val = getattr(item, id_field)
            if val and val.startswith(prefix):
                try:
                    nums.append(int(val.split("-")[-1]))
                except:
                    pass
    finally:
        db.close()
    return max(nums) + 1 if nums else 1



def condition_to_text(conditions):
    """将条件JSON树转为可读文字"""
    if not conditions:
        return ""
    if isinstance(conditions, str):
        try:
            conditions = json.loads(conditions)
        except (json.JSONDecodeError, TypeError):
            return conditions

    # 时序类型
    if isinstance(conditions, dict) and conditions.get("type") == "timing":
        delay = conditions.get("delay_ms", 0)
        return f"延迟{delay}ms后执行"

    op = conditions.get("op", "AND")
    items = conditions.get("items", [])

    if not items:
        return ""

    parts = []
    for item in items:
        if item.get("type") == "group":
            sub = condition_to_text(item)
            if sub:
                parts.append(f"({sub})")
        elif item.get("type") == "not":
            sub = condition_to_text({"op": "AND", "items": item.get("items", [])})
            if sub:
                parts.append(f"NOT ({sub})")
        else:
            # 叶子条件
            sig = item.get("signal", "?")
            cmp_op = item.get("op", "==")
            val = item.get("value", "?")
            unit = item.get("unit", "")
            if unit:
                parts.append(f"{sig} {cmp_op} {val}{unit}")
            else:
                parts.append(f"{sig} {cmp_op} {val}")

    connector = f" {op} "
    return connector.join(parts)


def condition_to_html(conditions, indent=0):
    """将条件树转为HTML格式（用于图表tooltip等）"""
    text = condition_to_text(conditions)
    if not text:
        return ""
    # 简单HTML格式化
    text = text.replace("AND", '<b style="color:#E65100">AND</b>')
    text = text.replace("OR", '<b style="color:#1565C0">OR</b>')
    text = text.replace("NOT", '<b style="color:#C62828">NOT</b>')
    return text


def empty_condition():
    """返回一个空的条件树模板"""
    return {"op": "AND", "items": []}


def add_leaf_condition(tree, signal="", op="==", value="", unit="", ecu=""):
    """往条件树添加一个叶子条件"""
    tree["items"].append({
    "type": "cond",
    "signal": signal,
    "op": op,
    "value": value,
        "unit": unit,
        "ecu": ecu
    })
    return tree


def add_group(tree, op="AND"):
    """往条件树添加一个子条件组"""
    tree["items"].append({
    "type": "group",
    "op": op,
    "items": []
    })
    return tree


def add_not_group(tree):
    """往条件树添加一个NOT条件组"""
    tree["items"].append({
    "type": "not",
    "items": []
    })
    return tree


# ========== vis.js 网络图生成 ==========
def generate_logic_graph(funcs, rels):
    """生成功能逻辑关系的vis.js网络图HTML"""
    # 构建节点
    nodes = []
    for f in funcs:
        color = {
            t("车身"): "#4CAF50", t("动力"): "#FF5722", t("底盘"): "#2196F3",
            t("座舱"): "#9C27B0", t("热管理"): "#FF9800", "ADAS": "#00BCD4",
            t("网关"): "#607D8B", t("充电"): "#8BC34A"
        }.get(f.category, "#757575")
        nodes.append({
            "id": f.id,
            "label": f"{f.func_id}\n{f.name}",
            "title": f"{f.func_id} - {f.name}\n功能域: {f.category or '-'}\nECU: {f.module or '-'}\nASIL: {f.asil_level or '-'}",
            "color": {"background": color, "border": color, "highlight": {"background": color, "border": "#333"}},
            "font": {"color": "#fff", "size": 12, "face": "Microsoft YaHei"},
            "shape": "box",
            "margin": 10,
            "borderWidth": 2
        })

    # 构建边
    edges = []
    rel_colors = {
        t("触发"): "#E65100", t("互锁"): "#C62828", t("联动"): "#2E7D32",
        t("依赖"): "#1565C0", t("时序"): "#6A1B9A", t("条件"): "#FF6F00",
        t("数据流"): "#00695C"
    }
    for r in rels:
        src_f = next((f for f in funcs if f.id == r.source_id), None)
        tgt_f = next((f for f in funcs if f.id == r.target_id), None)
        if not src_f or not tgt_f:
            continue

        cond_text = condition_to_text(r.conditions) if r.conditions else ""
        label = r.rel_type
        title_parts = [f"关系: {r.rel_type}"]
        if cond_text:
            title_parts.append(f"条件: {cond_text}")
        if r.description:
            title_parts.append(f"说明: {r.description}")

        edge_color = rel_colors.get(r.rel_type, "#757575")
        edges.append({
            "from": r.source_id,
            "to": r.target_id,
            "label": label,
            "title": "<br>".join(title_parts),
            "color": {"color": edge_color, "highlight": edge_color},
            "font": {"size": 10, "align": "middle", "face": "Microsoft YaHei"},
            "arrows": "to",
            "width": 2,
            "smooth": {"type": "cubicBezier"}
        })

    if not nodes:
        return t("<html><body style='font-family:Microsoft YaHei;display:flex;justify-content:center;align-items:center;height:100vh;color:#999'>暂无功能数据</body></html>")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ margin:0; padding:0; background:#1a1a2e; overflow:hidden; }}
#graph {{ width:100%; height:100vh; }}
#legend {{ position:absolute; top:10px; right:10px; background:rgba(26,26,46,0.9);
           border:1px solid #333; border-radius:8px; padding:12px; color:#eee;
           font-size:12px; font-family:Microsoft YaHei; z-index:10; }}
#legend .item {{ display:flex; align-items:center; margin:4px 0; }}
#legend .dot {{ width:14px; height:4px; margin-right:8px; border-radius:2px; }}
#info {{ position:absolute; bottom:10px; left:10px; background:rgba(26,26,46,0.9);
         border:1px solid #333; border-radius:8px; padding:12px; color:#eee;
         font-size:12px; font-family:Microsoft YaHei; max-width:400px; z-index:10;
         display:none; }}
#info h4 {{ margin:0 0 6px 0; color:#4FC3F7; }}
</style>
</head>
<body>
<div id="graph"></div>
<div id="legend">
  <div style="font-weight:bold;margin-bottom:6px;color:#4FC3F7">关系类型</div>
  <div class="item"><div class="dot" style="background:#E65100"></div>触发</div>
  <div class="item"><div class="dot" style="background:#C62828"></div>互锁</div>
  <div class="item"><div class="dot" style="background:#2E7D32"></div>联动</div>
  <div class="item"><div class="dot" style="background:#1565C0"></div>依赖</div>
  <div class="item"><div class="dot" style="background:#6A1B9A"></div>时序</div>
  <div class="item"><div class="dot" style="background:#FF6F00"></div>条件</div>
  <div class="item"><div class="dot" style="background:#00695C"></div>数据流</div>
</div>
<div id="info"><h4>详细信息</h4><div id="info-content"></div></div>
<script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"></script>
<script>
var nodes = new vis.DataSet({json.dumps(nodes, ensure_ascii=False)});
var edges = new vis.DataSet({json.dumps(edges, ensure_ascii=False)});
var container = document.getElementById('graph');
var data = {{ nodes: nodes, edges: edges }};
var options = {{
  physics: {{
    enabled: true,
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {{ gravitationalConstant: -80, centralGravity: 0.01, springLength: 200, springConstant: 0.02 }},
    stabilization: {{ iterations: 100 }}
  }},
  interaction: {{ hover: true, tooltipDelay: 200, zoomView: true, dragView: true }},
  edges: {{ font: {{ strokeWidth: 3 }} }}
}};
var network = new vis.Network(container, data, options);
network.on('click', function(params) {{
  var info = document.getElementById('info');
  var content = document.getElementById('info-content');
  if (params.edges.length > 0) {{
    var edgeId = params.edges[0];
    var edge = edges.get(edgeId);
    info.style.display = 'block';
    content.innerHTML = edge.title ? edge.title.replace(/\\n/g, '<br>') : edge.label;
  }} else if (params.nodes.length > 0) {{
    var nodeId = params.nodes[0];
    var node = nodes.get(nodeId);
    info.style.display = 'block';
    content.innerHTML = node.title ? node.title.replace(/\\n/g, '<br>') : node.label;
  }} else {{
    info.style.display = 'none';
  }}
}});
</script>
</body>
</html>"""
    return html


# ================================================================
#  📊 总览仪表盘
# ================================================================
def page_dashboard():
    st.title(t("📊 总览仪表盘"))
    render_notify()
    db = get_session()
    try:
        func_count = db.query(sql_func.count(Function.id)).filter(Function.project_id == current_project_id).scalar()
        sig_count = db.query(sql_func.count(Signal.id)).scalar()
        link_count = db.query(sql_func.count(FunctionSignal.id)).scalar()
        rel_count = db.query(sql_func.count(FuncRelation.id)).scalar()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(t("📋 车辆功能"), func_count)
        c2.metric(t("📡 CAN信号"), sig_count)
        c3.metric(t("🔗 关联绑定"), link_count)
        c4.metric(t("🔄 逻辑关系"), rel_count)

        st.divider()

        # 按域统计功能
        if func_count > 0:
            st.subheader(t("功能分布"))
            cats = db.query(
                Function.category, sql_func.count(Function.id)
            ).group_by(Function.category).all()
            if cats:
                df_cat = pd.DataFrame(cats, columns=[t("功能域"), t("数量")]).fillna(t("未分类"))
                st.bar_chart(df_cat.set_index("功能域"))

            # 按ECU统计
            st.subheader(t("ECU归属分布"))
            ecus = db.query(
                Function.module, sql_func.count(Function.id)
            ).group_by(Function.module).all()
            if ecus:
                df_ecu = pd.DataFrame(ecus, columns=["ECU", t("数量")]).fillna(t("未分配"))
                st.bar_chart(df_ecu.set_index("ECU"))

            # 最近添加的功能
            st.subheader(t("最近添加的功能"))
            recent = db.query(Function).order_by(Function.created_at.desc()).limit(5).all()
            if recent:
                df_r = pd.DataFrame([{
                    t("编号"): f.func_id,
                    t("名称"): f.name,
                    t("域"): f.category or "-",
                    "ECU": f.module or "-",
                    t("状态"): f.status
                } for f in recent])
                st.dataframe(df_r, use_container_width=True, hide_index=True)
        else:
            st.info(t("👋 欢迎使用！请先在「功能管理」中添加车辆功能。"))
    finally:
        db.close()


# ================================================================
#  📋 功能管理
# ================================================================
def page_functions():
    st.title(t("📋 功能管理"))
    render_notify()
    db = get_session()

    # 从数据库读取可配置列表
    categories = get_config(db, "category_list", [t("车身"), t("动力"), t("底盘"), t("座舱"), t("热管理"), "ADAS", t("网关"), t("充电"), t("其他")])
    modules = get_config(db, "ecu_list", ["VCU", "BCM", t("ICM/仪表"), "ADDC", "GW", "CCU", "BMS", "MCU", "ESC", "EPS", t("其他")])
    priorities = get_config(db, "priority_list", ["High", "Medium", "Low"])
    statuses = get_config(db, "status_list", ["Draft", "Review", "Approved", "Released"])
    asil_levels = get_config(db, "asil_list", ["-", "QM", "ASIL-A", "ASIL-B", "ASIL-C", "ASIL-D"])

    try:
        tab = st.radio(t("操作模式"), ["📋 功能列表", "➕ 新增功能", "✏️ 编辑功能"], horizontal=True, key="func_tab")

        # --- 功能列表 ---
        if tab == "📋 功能列表":
            funcs = db.query(Function).filter_by(project_id=current_project_id).order_by(Function.func_id).all()
            if not funcs:
                st.info(t("暂无功能数据，请新增。"))
            else:
                # 筛选
                c1, c2 = st.columns(2)
                with c1:
                    f_cat = st.selectbox(t("按域筛选"), [t("全部")] + categories, key="f_cat")
                with c2:
                    f_mod = st.selectbox(t("按ECU筛选"), [t("全部")] + modules, key="f_mod")

                filtered = funcs
                if f_cat != "全部":
                    filtered = [f for f in filtered if f.category == f_cat]
                if f_mod != "全部":
                    filtered = [f for f in filtered if f.module == f_mod]

                if filtered:
                    df = pd.DataFrame([{
                        t("编号"): f.func_id,
                        t("名称"): f.name,
                        t("功能域"): f.category or "-",
                        "ECU": f.module or "-",
                        t("优先级"): f.priority,
                        t("状态"): f.status,
                        "ASIL": f.asil_level or "-",
                        t("描述"): (f.description or "")[:50]
                    } for f in filtered])
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    st.caption(f"共 {len(filtered)} 条功能")

                    # 删除
                    with st.expander(t("🗑️ 删除功能")):
                        del_id = st.selectbox(t("选择要删除的功能"),
                                              [f.func_id for f in filtered],
                                              format_func=lambda x: next(
                                                  (f.func_id + " " + f.name for f in filtered if f.func_id == x), x),
                                              key="del_func")
                        if st.button(t("确认删除"), type="primary", key="del_func_btn"):
                            target = db.query(Function).filter_by(func_id=del_id).first()
                            if target:
                                db.delete(target)
                                db.commit()
                                notify(f"已删除 {del_id}")

                                st.rerun()

        # --- 新增功能 ---
        elif tab == "➕ 新增功能":
            with st.form("add_func"):
                st.subheader(t("新增车辆功能"))
                c1, c2, c3 = st.columns(3)
                with c1:
                    fid = st.text_input("功能编号", value=f"FUNC-{next_id('FUNC-', Function, 'func_id'):03d}")
                    fname = st.text_input("功能名称 *", placeholder="如: 左前门锁控制")
                    fcat = st.selectbox(t("功能域"), categories)
                with c2:
                    fmod = st.selectbox(t("归属ECU"), modules)
                    fpri = st.selectbox(t("优先级"), priorities, index=1)
                    fasil = st.selectbox(t("ASIL等级"), asil_levels)
                with c3:
                    fstatus = st.selectbox(t("状态"), statuses)
                fdesc = st.text_area(t("功能描述"), placeholder=t("描述该功能的输入、处理逻辑、输出..."),
                                     height=100)

                if st.form_submit_button(t("✅ 保存功能"), type="primary"):
                    if not fname:
                        st.error(t("功能名称不能为空"))
                    else:
                        new_func = Function(
                            func_id=fid, name=fname, category=fcat,
                            module=fmod, description=fdesc, priority=fpri,
                            status=fstatus, asil_level=fasil if fasil != "-" else None,
                            project_id=current_project_id
                        )
                        db.add(new_func)
                        db.commit()
                        notify(f"✅ 功能 {fid} — {fname} 已创建")
                        st.rerun()

        # --- 编辑功能 ---
        elif tab == "✏️ 编辑功能":
            funcs_all = db.query(Function).filter_by(project_id=current_project_id).order_by(Function.func_id).all()
            if not funcs_all:
                st.info(t("暂无功能可编辑。"))
            else:
                edit_sel = st.selectbox(t("选择功能"),
                                        funcs_all,
                                        format_func=lambda f: f"{f.func_id} — {f.name}",
                                        key="edit_func_sel")
                if edit_sel:
                    # 获取选中功能的当前值（避免ORM对象引用问题）
                    edit_id = edit_sel.func_id
                    # 从数据库重新获取最新数据
                    current_func = db.query(Function).filter_by(func_id=edit_id).first()

                    with st.form("edit_func"):
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            ename = st.text_input("功能名称", value=current_func.name)
                            ecat = st.selectbox(t("功能域"), categories,
                                                index=categories.index(current_func.category) if current_func.category in categories else 0)
                        with c2:
                            emod = st.selectbox(t("归属ECU"), modules,
                                                index=modules.index(current_func.module) if current_func.module in modules else 0)
                            epri = st.selectbox(t("优先级"), priorities,
                                                index=priorities.index(current_func.priority) if current_func.priority in priorities else 1)
                        with c3:
                            estatus = st.selectbox(t("状态"), statuses,
                                                   index=statuses.index(current_func.status) if current_func.status in statuses else 0)
                            easil = st.selectbox(t("ASIL等级"), asil_levels,
                                                 index=asil_levels.index(current_func.asil_level) if current_func.asil_level in asil_levels else 0)
                        edesc = st.text_area(t("功能描述"), value=current_func.description or "", height=100)

                        if st.form_submit_button(t("💾 保存修改"), type="primary"):
                            # 重新查询，确保只更新选中的那条记录
                            target = db.query(Function).filter_by(func_id=edit_id).first()
                            if target:
                                target.name = ename
                                target.category = ecat
                                target.module = emod
                                target.description = edesc
                                target.priority = epri
                                target.status = estatus
                                target.asil_level = easil if easil != "-" else None
                                target.updated_at = datetime.utcnow()
                                db.commit()
                                notify(f"✅ {edit_id} 已更新")
                                st.rerun()
    finally:
        db.close()


# ================================================================
#  📡 信号管理
# ================================================================
def page_signals():
    st.title(t("📡 CAN信号管理"))
    render_notify()
    db = get_session()

    byte_orders = ["Motorola", "Intel"]
    value_types = ["Unsigned", "Signed"]

    try:
        tab = st.radio(t("操作模式"), ["📡 信号列表", "➕ 新增信号", "✏️ 编辑信号"], horizontal=True, key="sig_tab")

        # --- 信号列表 ---
        if tab == "📡 信号列表":
            sigs = db.query(Signal).filter_by(project_id=current_project_id).order_by(Signal.signal_id).all()
            if not sigs:
                st.info(t("暂无信号数据，请新增。"))
            else:
                df = pd.DataFrame([{
                    t("编号"): s.signal_id,
                    t("信号名称"): s.name,
                    t("报文"): s.message_name or "-",
                    "CAN ID": s.message_id or "-",
                    t("起始位"): s.start_bit,
                    t("位长"): s.bit_length,
                    t("精度"): s.factor,
                    t("偏移"): s.offset,
                    t("范围"): f"{s.min_value if s.min_value is not None else '?'}~{s.max_value if s.max_value is not None else '?'}" if (s.min_value is not None or s.max_value is not None) else "-",
                    t("单位"): s.unit or "-",
                    t("周期ms"): s.cycle_time or "-",
                    t("字节序"): s.byte_order or "-",
                    t("描述"): (s.description or "")[:30]
                } for s in sigs])
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.caption(f"共 {len(sigs)} 条信号")

                with st.expander(t("🗑️ 删除信号")):
                    del_sid = st.selectbox(t("选择要删除的信号"),
                                           [s.signal_id for s in sigs],
                                           format_func=lambda x: next(
                                               (s.signal_id + " " + s.name for s in sigs if s.signal_id == x), x),
                                           key="del_sig")
                    if st.button(t("确认删除"), type="primary", key="del_sig_btn"):
                        target = db.query(Signal).filter_by(signal_id=del_sid).first()
                        if target:
                            db.delete(target)
                            db.commit()
                            notify(f"已删除 {del_sid}")

                            st.rerun()

        # --- 新增信号 ---
        elif tab == "➕ 新增信号":
            with st.form("add_sig"):
                st.subheader(t("新增CAN信号"))
                c1, c2, c3 = st.columns(3)
                with c1:
                    sid = st.text_input("信号编号", value=next_id("SIG-", Signal, "signal_id"))
                    sname = st.text_input("信号名称 *", placeholder="如: DoorLock_Sts")
                    smsg = st.text_input("报文名称", placeholder="如: BCM_DoorStatus_0x301")
                with c2:
                    smsgid = st.text_input("CAN ID (hex)", placeholder="0x301")
                    sdlc = st.number_input("DLC (Byte)", min_value=1, max_value=64, value=8)
                    sstart = st.number_input("起始位", min_value=0, max_value=511, value=0)
                with c3:
                    sbits = st.number_input("位长", min_value=1, max_value=64, value=8)
                    sfactor = st.number_input("精度/分辨率", value=1.0, format="%.4f")
                    soffset = st.number_input("偏移量", value=0.0, format="%.2f")

                c4, c5, c6 = st.columns(3)
                with c4:
                    smin = st.number_input("物理最小值", value=0.0, format="%.2f")
                    smax = st.number_input("物理最大值", value=255.0, format="%.2f")
                with c5:
                    sunit = st.text_input("单位", placeholder="如: rpm, ℃, kPa")
                    scycle = st.number_input("发送周期 (ms)", min_value=0, value=100, step=10)
                with c6:
                    sbo = st.selectbox(t("字节序"), byte_orders)
                    svt = st.selectbox(t("值类型"), value_types)

                sdesc = st.text_area(t("信号描述"), height=80)

                if st.form_submit_button(t("✅ 保存信号"), type="primary"):
                    if not sname:
                        st.error(t("信号名称不能为空"))
                    else:
                        new_sig = Signal(
                            signal_id=sid, name=sname, message_name=smsg,
                            message_id=smsgid, dlc=sdlc, start_bit=sstart,
                            bit_length=sbits, factor=sfactor, offset=soffset,
                            min_value=smin, max_value=smax, unit=sunit,
                            byte_order=sbo, value_type=svt, cycle_time=scycle,
                            description=sdesc
                        )
                        db.add(new_sig)
                        db.commit()
                        notify(f"✅ 信号 {sid} — {sname} 已创建")

                        st.rerun()

        # --- 编辑信号 ---
        elif tab == "✏️ 编辑信号":
            sigs_all = db.query(Signal).order_by(Signal.signal_id).all()
            if not sigs_all:
                st.info(t("暂无信号可编辑。"))
            else:
                edit_sel = st.selectbox(t("选择信号"),
                                        sigs_all,
                                        format_func=lambda s: f"{s.signal_id} — {s.name}",
                                        key="edit_sig_sel")
                if edit_sel:
                    # 获取选中信号的当前值（避免ORM对象引用问题）
                    edit_id = edit_sel.signal_id
                    # 从数据库重新获取最新数据
                    current_sig = db.query(Signal).filter_by(signal_id=edit_id).first()

                    with st.form("edit_sig"):
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            ename = st.text_input("信号名称", value=current_sig.name)
                            emsg = st.text_input("报文名称", value=current_sig.message_name or "")
                            emsgid = st.text_input("CAN ID", value=current_sig.message_id or "")
                        with c2:
                            edlc = st.number_input("DLC", min_value=1, max_value=64, value=safe_num(current_sig.dlc, int, 8))
                            estart = st.number_input("起始位", min_value=0, max_value=511, value=safe_num(current_sig.start_bit, int, 0))
                            ebits = st.number_input("位长", min_value=1, max_value=64, value=safe_num(current_sig.bit_length, int, 8))
                        with c3:
                            efactor = st.number_input("精度", value=safe_num(current_sig.factor, float, 1.0), format="%.4f")
                            eoffset = st.number_input("偏移", value=safe_num(current_sig.offset, float, 0.0), format="%.2f")
                            eunit = st.text_input("单位", value=current_sig.unit or "")

                        c4, c5 = st.columns(2)
                        with c4:
                            emin = st.number_input("最小值", value=safe_num(current_sig.min_value, float, 0.0), format="%.2f")
                            emax = st.number_input("最大值", value=safe_num(current_sig.max_value, float, 255.0), format="%.2f")
                        with c5:
                            ecycle = st.number_input("周期ms", min_value=0, value=safe_num(current_sig.cycle_time, int, 100), step=10)
                            edesc = st.text_area(t("描述"), value=current_sig.description or "", height=80)

                        if st.form_submit_button(t("💾 保存修改"), type="primary"):
                            # 重新查询，确保只更新选中的那条记录
                            target = db.query(Signal).filter_by(signal_id=edit_id).first()
                            if target:
                                target.name = ename
                                target.message_name = emsg
                                target.message_id = emsgid
                                target.dlc = edlc
                                target.start_bit = estart
                                target.bit_length = ebits
                                target.factor = efactor
                                target.offset = eoffset
                                target.unit = eunit
                                target.min_value = emin
                                target.max_value = emax
                                target.cycle_time = ecycle
                                target.description = edesc
                                db.commit()
                                notify(f"✅ {edit_id} 已更新")
                                st.rerun()
    finally:
        db.close()


# ================================================================
#  🔗 功能-信号关联
# ================================================================
def page_func_signal():
    st.title(t("🔗 功能-信号关联"))
    render_notify()
    db = get_session()

    directions = ["Input", "Output", "Feedback"]

    try:
        funcs = db.query(Function).order_by(Function.func_id).all()
        sigs = db.query(Signal).order_by(Signal.signal_id).all()

        if not funcs or not sigs:
            st.warning(t("请先添加功能和信号数据。"))
            return

        tab_bind, tab_view = st.tabs(["➕ 绑定信号", "📋 关联列表"])

        with tab_bind:
            c1, c2, c3 = st.columns(3)
            with c1:
                sel_func = st.selectbox(t("选择功能"), funcs,
                                        format_func=lambda f: f"{f.func_id} — {f.name}")
            with c2:
                # 搜索框+自动弹出 — 类似Excel筛选效果
                sig_labels = [t("(输入关键字搜索...)")] + [
                    f"{s.signal_id} — {s.name}  ({s.message_name or ''})"
                    for s in sigs
                ]
                chosen = st.selectbox(t("选择信号"), sig_labels, key="sig_search_select")
                sel_sig = None
                if chosen and chosen != "(输入关键字搜索...)":
                    sig_id = chosen.split(" — ")[0]
                    for s in sigs:
                        if s.signal_id == sig_id:
                            sel_sig = s
                            break
                elif chosen == "(输入关键字搜索...)":
                    pass  # 默认空，不选中
            with c3:
                sel_dir = st.selectbox(t("信号方向"), directions)

            usage = st.text_input("用途说明", placeholder="如: BCM读取此信号判断车门锁定状态")
            required = st.checkbox(t("必需信号"), value=True)

            if st.button(t("✅ 绑定"), type="primary"):
                if not sel_sig:
                    st.warning(t("请先搜索并选择信号"))
                else:
                    existing = db.query(FunctionSignal).filter_by(
                        function_id=sel_func.id, signal_id=sel_sig.id, direction=sel_dir
                    ).first()
                    if existing:
                        st.warning(t("该关联已存在！"))
                    else:
                        link = FunctionSignal(
                            function_id=sel_func.id, signal_id=sel_sig.id,
                            direction=sel_dir, usage_desc=usage, is_required=required
                        )
                        db.add(link)
                        db.commit()
                        notify(f"✅ 已绑定: {sel_func.func_id} ↔ {sel_sig.signal_id} ({sel_dir})")

                        st.rerun()

        with tab_view:
            links = db.query(FunctionSignal).all()
            if not links:
                st.info(t("暂无关联数据。"))
            else:
                # 按功能筛选
                func_opts = ["全部"] + [f"{f.func_id} — {f.name}" for f in funcs]
                f_filter = st.selectbox(t("按功能筛选"), func_opts, key="link_filter")

                rows = []
                for l in links:
                    if f_filter != "全部":
                        fobj = db.query(Function).get(l.function_id)
                        if f"{fobj.func_id} — {fobj.name}" != f_filter:
                            continue
                    fobj = db.query(Function).get(l.function_id)
                    sobj = db.query(Signal).get(l.signal_id)
                    rows.append({
                        t("功能"): f"{fobj.func_id} {fobj.name}",
                        t("信号"): f"{sobj.signal_id} {sobj.name}",
                        t("方向"): l.direction,
                        t("用途"): l.usage_desc or "-",
                        t("必需"): "✅" if l.is_required else "❌"
                    })

                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                    st.caption(f"共 {len(rows)} 条关联")

                    # 解绑
                    with st.expander(t("🗑️ 解除绑定")):
                        del_opts = [f"{i}: {r[t('功能')]} ↔ {r[t('信号')]} ({r[t('方向')]})" for i, r in enumerate(rows)]
                        del_sel = st.selectbox(t("选择要解除的关联"), del_opts, key="unbind_sel")
                        if st.button(t("确认解除"), type="primary", key="unbind_btn"):
                            idx = int(del_sel.split(":")[0])
                            target_link = links[idx]
                            db.delete(target_link)
                            db.commit()
                            notify(t("已解除绑定"))

                            st.rerun()
    finally:
        db.close()


# ================================================================
#  🔄 逻辑关系
# ================================================================
def page_relations():
    st.title(t("🔄 功能间逻辑关系"))
    render_notify()
    db = get_session()

    rel_types = ["触发", "互锁", "联动", "依赖", "时序", "条件", "数据流"]
    cmp_ops = ["==", "!=", ">", "<", ">=", "<=", t("包含")]
    logic_ops = ["AND", "OR"]

    try:
        funcs = db.query(Function).order_by(Function.func_id).all()
        if len(funcs) < 2:
            st.warning(t("至少需要2个功能才能建立关系。"))
            return

        # 获取已有信号列表供条件编辑器用
        all_signals = db.query(Signal).order_by(Signal.signal_id).all()
        signal_names = [s.name for s in all_signals]

        tab_graph, tab_dbc, tab_add, tab_list, tab_sf = st.tabs(["📊 关系网络图", "📥 从数据库生成", "➕ 新增关系", "📋 关系列表", "📡 信号-功能"])

        # ========== 关系网络图 ==========
        with tab_graph:
            rels = db.query(FuncRelation).all()
            if not rels:
                st.info(t("暂无逻辑关系，请先添加。"))
            else:
                st.caption(t("🖱️ 鼠标拖拽节点可调整布局 | 点击边/节点查看详情 | 滚轮缩放"))
                graph_html = generate_logic_graph(funcs, rels)
                components.html(graph_html, height=550, scrolling=False)

                # 关系统计
                st.divider()
                stat_cols = st.columns(len(rel_types))
                for i, rt in enumerate(rel_types):
                    count = sum(1 for r in rels if r.rel_type == rt)
                    with stat_cols[i]:
                        st.metric(rt, count)

        # ========== 从数据库自动生成逻辑关系 ==========
        with tab_dbc:
            st.subheader(t("📥 从数据库自动分析ECU间信号流"))
            st.caption(t("根据已导入的信号数据，按报文聚合推导ECU间数据流关系"))

            sigs = db.query(Signal).filter_by(project_id=current_project_id).all()
            if not sigs:
                st.warning(t("当前车型无信号数据，请先在DBC导入或Excel通讯矩阵中导入信号。"))
            else:
                # 按报文分组，提取发送节点
                import re
                msg_groups = {}
                for s in sigs:
                    msg = s.message_name or t("未知报文")
                    if msg not in msg_groups:
                        # 从description提取发送节点
                        sender = ""
                        if s.description:
                            m = re.search(rt('发送节点:\s*(\S+)'), s.description)
                            if m:
                                sender = m.group(1)
                        msg_groups[msg] = {"sender": sender or (s.module or "?"), "signals": [], "msg_id": s.message_id or ""}
                    msg_groups[msg]["signals"].append(s.name)

                # 汇总ECU间关系
                ecu_rels = {}
                for msg_name, info in msg_groups.items():
                    tx = info["sender"]
                    if tx == "?" or not tx:
                        continue
                    if tx not in ecu_rels:
                        ecu_rels[tx] = {}
                    # 找到目标ECU：从功能管理中匹配
                    ecu_list = get_config(db, "ecu_list", [])
                    for ecu in ecu_list:
                        if ecu != tx:
                            ecu_rels[tx].setdefault(ecu, {"messages": [], "signals": []})
                            ecu_rels[tx][ecu]["messages"].append(msg_name)
                            ecu_rels[tx][ecu]["signals"].extend(info["signals"])

                # 过滤有实际信号的关系
                rel_summary = {}
                for tx, targets in ecu_rels.items():
                    for rx, data in targets.items():
                        if data["signals"]:
                            key = (tx, rx)
                            rel_summary[key] = {
                                "tx_ecu": tx, "rx_ecu": rx,
                                "messages": data["messages"],
                                "total_signals": len(data["signals"])
                            }

                if not rel_summary:
                    st.info(t("未能提取到ECU间关系。请确保信号描述中包含「发送节点」信息。"))
                else:
                    st.metric(t("识别到的ECU关系"), len(rel_summary))

                    summary_df = pd.DataFrame([{
                        t("发送ECU"): v["tx_ecu"],
                        t("接收ECU"): v["rx_ecu"],
                        t("报文数"): len(v["messages"]),
                        t("信号总数"): v["total_signals"],
                        t("报文示例"): ", ".join(v["messages"][:3])
                    } for v in rel_summary.values()])
                    st.dataframe(summary_df, use_container_width=True, hide_index=True)

                    if st.button(t("🚀 一键生成数据流关系"), type="primary", key="btn_gen_db_rels"):
                        imported = 0
                        skipped = 0
                        for key, v in rel_summary.items():
                            src_func = db.query(Function).filter_by(
                                project_id=current_project_id, module=v["tx_ecu"]
                            ).first()
                            tgt_func = db.query(Function).filter_by(
                                project_id=current_project_id, module=v["rx_ecu"]
                            ).first()
                            if not src_func or not tgt_func:
                                skipped += 1
                                continue
                            existing = db.query(FuncRelation).filter_by(
                                project_id=current_project_id,
                                source_id=src_func.id, target_id=tgt_func.id,
                                rel_type=t("数据流")
                            ).first()
                            if existing:
                                skipped += 1
                                continue
                            rel = FuncRelation(
                                project_id=current_project_id,
                                source_id=src_func.id, target_id=tgt_func.id,
                                rel_type=t("数据流"),
                                description=f"[DB] {v['tx_ecu']}→{v['rx_ecu']}: {v['total_signals']}信号",
                                conditions=json.dumps({"op": "AND", "items": []}, ensure_ascii=False)
                            )
                            db.add(rel)
                            imported += 1
                        db.commit()
                        notify(f"✅ 生成完成！新增 {imported} 条关系，跳过 {skipped} 条（缺少对应ECU功能记录）")
                        st.rerun()

        # ========== 新增关系 ==========
        with tab_add:
            # 显示上一次保存的结果通知
            if "rel_notify" in st.session_state:
                n = st.session_state.rel_notify
                if n["type"] == "success":
                    st.success(n["msg"])
                elif n["type"] == "error":
                    st.error(n["msg"])
                if n.get("detail"):
                    st.info(n["detail"])
                del st.session_state.rel_notify

            st.subheader(t("基本信息"))
            c1, c2, c3 = st.columns(3)
            with c1:
                src = st.selectbox(t("源功能"), funcs,
                                   format_func=lambda f: f"{f.func_id} — {f.name}",
                                   key="rel_src")
            with c2:
                rtype = st.selectbox(t("关系类型"), rel_types)
            with c3:
                tgt = st.selectbox(t("目标功能"), funcs,
                                   format_func=lambda f: f"{f.func_id} — {f.name}",
                                   key="rel_tgt")

            st.divider()

            # ===== 根据关系类型显示不同的二级操作界面 =====
            cond_data = None  # 最终存入 conditions 字段的 JSON

            if rtype == "条件":
                st.subheader(t("🧩 条件编辑器"))
                st.caption(t("构建触发条件 — 支持 AND/OR/NOT 组合。例如：车门未关 AND 挡位不在P挡"))

                # 用 session_state 维护条件树
                if "cond_tree" not in st.session_state:
                    st.session_state.cond_tree = empty_condition()
                if "cond_counter" not in st.session_state:
                    st.session_state.cond_counter = 0

                tree = st.session_state.cond_tree

                # 顶层逻辑运算符
                tree["op"] = st.radio(t("顶层逻辑运算"), logic_ops,
                                       index=0 if tree["op"] == "AND" else 1,
                                       horizontal=True, key="cond_top_op")
                tree["op"] = st.session_state.cond_top_op

                # 显示当前条件树
                cond_text = condition_to_text(tree)
                if cond_text:
                    st.markdown(f"**当前条件：** `{cond_text}`")
                else:
                    st.caption(t("（暂无条件 — 直接保存则为无条件关系）"))

                # 条件操作按钮
                col_add, col_grp, col_not, col_clr = st.columns(4)
                with col_add:
                    if st.button(t("➕ 添加条件"), key="btn_add_cond"):
                        st.session_state.cond_counter += 1
                        add_leaf_condition(tree, signal="", op="==", value="")
                        st.session_state.cond_tree = tree
                        st.rerun()
                with col_grp:
                    if st.button(t("📁 添加条件组(AND/OR)"), key="btn_add_grp"):
                        add_group(tree, "AND")
                        st.session_state.cond_tree = tree
                        st.rerun()
                with col_not:
                    if st.button(t("🚫 添加NOT条件"), key="btn_add_not"):
                        add_not_group(tree)
                        st.session_state.cond_tree = tree
                        st.rerun()
                with col_clr:
                    if st.button(t("🗑️ 清空条件"), key="btn_clr_cond"):
                        st.session_state.cond_tree = empty_condition()
                        st.rerun()

                # 渲染每个条件项
                items = tree.get("items", [])
                for idx, item in enumerate(items):
                    with st.container():
                        ic1, ic2, ic3, ic4, ic5 = st.columns([3, 1.5, 1.5, 2, 0.5])
                        item_key = f"cond_item_{idx}"

                        if item.get("type") == "cond":
                            with ic1:
                                sig_options = [t("（手动输入）")] + signal_names
                                sel = st.selectbox(f"条件{idx+1} 信号", sig_options,
                                                   key=f"{item_key}_sig_sel")
                                if sel == "（手动输入）":
                                    item["signal"] = st.text_input("信号名", value=item.get("signal", ""),
                                                                   key=f"{item_key}_sig_manual",
                                                                   label_visibility="collapsed",
                                                                   placeholder=t("如: DoorOpen_Sts"))
                                else:
                                    item["signal"] = sel
                            with ic2:
                                item["op"] = st.selectbox(t("运算符"), cmp_ops,
                                                           index=cmp_ops.index(item.get("op", "==")),
                                                           key=f"{item_key}_op",
                                                           label_visibility="collapsed")
                            with ic3:
                                item["value"] = st.text_input("值", value=str(item.get("value", "")),
                                                              key=f"{item_key}_val",
                                                              label_visibility="collapsed",
                                                              placeholder="1")
                            with ic4:
                                item["unit"] = st.text_input("单位", value=item.get("unit", ""),
                                                             key=f"{item_key}_unit",
                                                             label_visibility="collapsed",
                                                             placeholder=t("如: rpm, ℃"))
                            with ic5:
                                st.write("")
                                if st.button("❌", key=f"{item_key}_del"):
                                    items.pop(idx)
                                    st.session_state.cond_tree = tree
                                    st.rerun()

                        elif item.get("type") == "group":
                            item["op"] = st.selectbox(f"组{idx+1} 逻辑", logic_ops,
                                                       index=0 if item.get("op", "AND") == "AND" else 1,
                                                       key=f"{item_key}_grp_op")
                            sub_items = item.get("items", [])
                            for si, sub in enumerate(sub_items):
                                sc1, sc2, sc3, sc4, sc5 = st.columns([3, 1.5, 1.5, 2, 0.5])
                                sub_key = f"{item_key}_sub_{si}"
                                with sc1:
                                    sig_options = [t("（手动输入）")] + signal_names
                                    sel = st.selectbox(f"  子条件{si+1}", sig_options,
                                                       key=f"{sub_key}_sig_sel")
                                    if sel == "（手动输入）":
                                        sub["signal"] = st.text_input("信号名", value=sub.get("signal", ""),
                                                                       key=f"{sub_key}_sig_manual",
                                                                       label_visibility="collapsed")
                                    else:
                                        sub["signal"] = sel
                                with sc2:
                                    sub["op"] = st.selectbox(t("运算符"), cmp_ops,
                                                              index=cmp_ops.index(sub.get("op", "==")),
                                                              key=f"{sub_key}_op",
                                                              label_visibility="collapsed")
                                with sc3:
                                    sub["value"] = st.text_input("值", value=str(sub.get("value", "")),
                                                                  key=f"{sub_key}_val",
                                                                  label_visibility="collapsed")
                                with sc4:
                                    sub["unit"] = st.text_input("单位", value=sub.get("unit", ""),
                                                                 key=f"{sub_key}_unit",
                                                                 label_visibility="collapsed")
                                with sc5:
                                    st.write("")
                                    if st.button("❌", key=f"{sub_key}_del"):
                                        sub_items.pop(si)
                                        st.session_state.cond_tree = tree
                                        st.rerun()
                            sc_a, sc_b = st.columns(2)
                            with sc_a:
                                if st.button(f"➕ 组{idx+1}添加条件", key=f"{item_key}_add_sub"):
                                    sub_items.append({"type": "cond", "signal": "", "op": "==", "value": "", "unit": ""})
                                    st.session_state.cond_tree = tree
                                    st.rerun()
                            with sc_b:
                                if st.button(f"🗑️ 删除组{idx+1}", key=f"{item_key}_del_grp"):
                                    items.pop(idx)
                                    st.session_state.cond_tree = tree
                                    st.rerun()

                        elif item.get("type") == "not":
                            st.markdown(f"**🚫 NOT 条件{idx+1}**")
                            sub_items = item.get("items", [])
                            for si, sub in enumerate(sub_items):
                                sc1, sc2, sc3, sc4, sc5 = st.columns([3, 1.5, 1.5, 2, 0.5])
                                sub_key = f"{item_key}_not_{si}"
                                with sc1:
                                    sig_options = [t("（手动输入）")] + signal_names
                                    sel = st.selectbox(f"  NOT条件{si+1}", sig_options,
                                                       key=f"{sub_key}_sig_sel")
                                    if sel == "（手动输入）":
                                        sub["signal"] = st.text_input("信号名", value=sub.get("signal", ""),
                                                                       key=f"{sub_key}_sig_manual",
                                                                       label_visibility="collapsed")
                                    else:
                                        sub["signal"] = sel
                                with sc2:
                                    sub["op"] = st.selectbox(t("运算符"), cmp_ops,
                                                              index=cmp_ops.index(sub.get("op", "==")),
                                                              key=f"{sub_key}_op",
                                                              label_visibility="collapsed")
                                with sc3:
                                    sub["value"] = st.text_input("值", value=str(sub.get("value", "")),
                                                                  key=f"{sub_key}_val",
                                                                  label_visibility="collapsed")
                                with sc4:
                                    sub["unit"] = st.text_input("单位", value=sub.get("unit", ""),
                                                                 key=f"{sub_key}_unit",
                                                                 label_visibility="collapsed")
                                with sc5:
                                    st.write("")
                                    if st.button("❌", key=f"{sub_key}_del"):
                                        sub_items.pop(si)
                                        st.session_state.cond_tree = tree
                                        st.rerun()
                            nc_a, nc_b = st.columns(2)
                            with nc_a:
                                if st.button(f"➕ NOT{idx+1}添加条件", key=f"{item_key}_add_not"):
                                    sub_items.append({"type": "cond", "signal": "", "op": "==", "value": "", "unit": ""})
                                    st.session_state.cond_tree = tree
                                    st.rerun()
                            with nc_b:
                                if st.button(f"🗑️ 删除NOT{idx+1}", key=f"{item_key}_del_not"):
                                    items.pop(idx)
                                    st.session_state.cond_tree = tree
                                    st.rerun()

                # 保存条件树的引用
                cond_data = tree if tree.get("items") else None

            elif rtype == "时序":
                st.subheader(t("⏱ 时序参数设置"))
                st.caption(t("设置源功能触发后到目标功能执行的延迟时间"))
                delay_col1, delay_col2 = st.columns([1, 3])
                with delay_col1:
                    delay_ms = st.number_input("延迟时间", min_value=0, max_value=60000,
                                               value=500, step=100, key="rel_delay")
                with delay_col2:
                    st.selectbox(t("单位"), [t("毫秒(ms)")], key="rel_delay_unit",
                                 label_visibility="collapsed")
                st.markdown(f"**时序含义：** 源功能执行 → 等待 `{delay_ms}ms` → 目标功能执行")
                cond_data = {"type": "timing", "delay_ms": delay_ms}

            else:
                # 触发/互锁/联动/依赖/数据流 — 无需额外二级界面
                st.info(f"已选择关系类型「{rtype}」，直接保存即可，无需额外参数。")

            st.divider()

            # 描述
            if rtype == "条件":
                auto_desc = condition_to_text(tree) if cond_data else ""
            elif rtype == "时序":
                auto_desc = f"延迟{delay_ms}ms后执行"
            else:
                auto_desc = ""
            rdesc = st.text_area(t("补充说明（可选）"),
                                 placeholder=f"补充{ {rtype} }关系的业务含义",
                                 height=60)

            # 保存
            if st.button(t("✅ 保存关系"), type="primary", key="btn_save_rel"):
                if src.id == tgt.id:
                    st.error(t("源和目标不能相同！"))
                else:
                    # 验证条件完整性
                    if rtype == "条件" and cond_data:
                        for item in cond_data.get("items", []):
                            if item.get("type") == "cond" and not item.get("signal", "").strip():
                                st.error(t("存在未填写信号名的条件，请补全或删除空条件！"))
                                st.stop()
                            if item.get("type") in ("group", "not"):
                                for sub in item.get("items", []):
                                    if sub.get("type") == "cond" and not sub.get("signal", "").strip():
                                        st.error(t("条件组中存在未填写信号名的条件，请补全或删除！"))
                                        st.stop()

                    final_desc = f"{auto_desc}\n{rdesc}".strip() if rdesc else auto_desc
                    rel = FuncRelation(
                        source_id=src.id, target_id=tgt.id,
                        rel_type=rtype,
                        description=final_desc if final_desc else rdesc,
                        conditions=json.dumps(cond_data, ensure_ascii=False) if cond_data else None
                    )
                    db.add(rel)
                    db.commit()
                    # 清空条件树
                    if "cond_tree" in st.session_state:
                        st.session_state.cond_tree = empty_condition()
                    # 存到session_state，rerun后显示
                    st.session_state.rel_notify = {
                        "type": "success",
                        "msg": f"✅ 已创建: {src.func_id} --[{rtype}]--> {tgt.func_id}",
                        "detail": f"详情: {auto_desc}" if auto_desc else ""
                    }
                    st.rerun()

        # ========== 关系列表 ==========
        with tab_list:
            rels = db.query(FuncRelation).all()
            if not rels:
                st.info(t("暂无逻辑关系。"))
            else:
                rows = []
                for r in rels:
                    src_f = db.query(Function).get(r.source_id)
                    tgt_f = db.query(Function).get(r.target_id)
                    cond_text = condition_to_text(r.conditions) if r.conditions else "-"
                    rows.append({
                        "ID": r.id,
                        t("源功能"): f"{src_f.func_id} {src_f.name}",
                        t("关系"): r.rel_type,
                        t("目标功能"): f"{tgt_f.func_id} {tgt_f.name}",
                        t("条件"): cond_text[:60] if cond_text != "-" else "-",
                        t("说明"): (r.description or "-")[:40]
                    })
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.caption(f"共 {len(rows)} 条关系")

                # 查看详情
                with st.expander(t("🔍 查看关系详情")):
                    detail_opts = {r.id: r for r in rels}
                    detail_sel = st.selectbox(t("选择关系"), rels,
                                              format_func=lambda r: f"{r.id}: {next((f.func_id for f in funcs if f.id == r.source_id), '?')} --{r.rel_type}--> {next((f.func_id for f in funcs if f.id == r.target_id), '?')}",
                                              key="detail_rel")
                    if detail_sel:
                        d_src = db.query(Function).get(detail_sel.source_id)
                        d_tgt = db.query(Function).get(detail_sel.target_id)
                        st.markdown(f"**{d_src.func_id} {d_src.name}** → **{d_tgt.func_id} {d_tgt.name}**")
                        st.markdown(f"关系类型: `{detail_sel.rel_type}`")
                        if detail_sel.conditions:
                            cond = json.loads(detail_sel.conditions)
                            st.markdown(f"**条件表达式:**")
                            st.code(condition_to_text(cond), language=None)
                            st.json(cond)
                        if detail_sel.description:
                            st.markdown(f"说明: {detail_sel.description}")

                # 删除
                with st.expander(t("🗑️ 删除关系")):
                    del_opts = [f"{r.id}: {rows[i][t('源功能')]} --{rows[i][t('关系')]}--> {rows[i][t('目标功能')]}"
                                for i, r in enumerate(rels)]
                    del_sel = st.selectbox(t("选择要删除的关系"), del_opts, key="del_rel")
                    if st.button(t("确认删除"), type="primary", key="del_rel_btn"):
                        rid = int(del_sel.split(":")[0])
                        target = db.query(FuncRelation).get(rid)
                        if target:
                            db.delete(target)
                            db.commit()
                            notify(t("已删除"))

                            st.rerun()

        # ========== 信号-功能关系 ==========
        with tab_sf:
            st.subheader(t("📡 信号-功能关系"))
            st.caption(t("定义信号满足条件 → 触发功能，或功能执行 → 影响信号"))

            sf_directions = ["signal_to_func", "func_to_signal"]
            sf_rel_types = ["触发", "报警", "联动", "互锁"]

            sf_tab_add, sf_tab_list = st.tabs(["➕ 新增关系", "📋 关系列表"])

            with sf_tab_add:
                c1, c2, c3 = st.columns(3)
                with c1:
                    sf_sig = st.selectbox(t("信号"), all_signals,
                                          format_func=lambda s: f"{s.name}", key="sf_sig")
                with c2:
                    sf_dir = st.selectbox(t("方向"), sf_directions,
                                          format_func=lambda d: t("信号→功能") if d == "signal_to_func" else t("功能→信号"),
                                          key="sf_dir")
                with c3:
                    sf_type = st.selectbox(t("关系类型"), sf_rel_types, key="sf_type")

                sf_func = st.selectbox(t("功能"), funcs,
                                       format_func=lambda f: f"{f.func_id} — {f.name}", key="sf_func")

                # 条件编辑器（signal→func方向时显示）
                sf_conditions = None
                if sf_dir == "signal_to_func":
                    st.divider()
                    st.subheader(t("🧩 条件编辑器"))
                    st.caption(t("构建触发条件 — 支持 AND/OR/NOT 组合"))
                    if "sf_cond_tree" not in st.session_state:
                        tree = empty_condition()
                        add_leaf_condition(tree)  # 默认给一个空条件行
                        st.session_state.sf_cond_tree = tree

                    tree = st.session_state.sf_cond_tree
                    tree["op"] = st.radio(t("顶层逻辑运算"), logic_ops,
                                          index=0 if tree.get("op", "AND") == "AND" else 1,
                                          horizontal=True, key="sf_cond_op")
                    tree["op"] = st.session_state.sf_cond_op

                    cond_text = condition_to_text(tree)
                    if cond_text:
                        st.markdown(f"**当前条件：** `{cond_text}`")
                    else:
                        st.caption(t("（无额外条件则直接触发）"))

                    col_add, col_grp, col_not, col_clr = st.columns(4)
                    with col_add:
                        if st.button(t("➕ 添加条件"), key="sf_add"):
                            add_leaf_condition(tree)
                            st.rerun()
                    with col_grp:
                        if st.button(t("📁 条件组"), key="sf_grp"):
                            add_group(tree)
                            st.rerun()
                    with col_not:
                        if st.button("🚫 NOT", key="sf_not"):
                            add_not_group(tree)
                            st.rerun()
                    with col_clr:
                        if st.button(t("🗑️ 清空"), key="sf_clr"):
                            st.session_state.sf_cond_tree = empty_condition()
                            st.rerun()

                    items = tree.get("items", [])
                    for idx, item in enumerate(items):
                        ik = f"sf_{idx}"
                        if item.get("type") == "cond":
                            ic1, ic2, ic3, ic4, ic5 = st.columns([3, 1.5, 1.5, 2, 0.5])
                            with ic1:
                                sig_options = [t("（手动输入）")] + signal_names
                                sel = st.selectbox(f"条件{idx+1}", sig_options, key=f"{ik}_sigsel")
                                if sel == "（手动输入）":
                                    item["signal"] = st.text_input("", value=item.get("signal", ""),
                                                                   key=f"{ik}_sig", label_visibility="collapsed",
                                                                   placeholder=t("信号名"))
                                else:
                                    item["signal"] = sel
                            with ic2:
                                item["op"] = st.selectbox("", cmp_ops,
                                                          index=cmp_ops.index(item.get("op", "==")),
                                                          key=f"{ik}_op", label_visibility="collapsed")
                            with ic3:
                                item["value"] = st.text_input("", value=str(item.get("value", "")),
                                                              key=f"{ik}_val", label_visibility="collapsed")
                            with ic4:
                                item["unit"] = st.text_input("", value=item.get("unit", ""),
                                                             key=f"{ik}_unit", label_visibility="collapsed",
                                                             placeholder="km/h")
                            with ic5:
                                if st.button("❌", key=f"{ik}_del"):
                                    items.pop(idx)
                                    st.rerun()
                        elif item.get("type") == "group":
                            item["op"] = st.selectbox(f"组{idx+1}", logic_ops,
                                                       index=0 if item.get("op", "AND") == "AND" else 1,
                                                       key=f"{ik}_gop")
                            for si, sub in enumerate(item.get("items", [])):
                                sk = f"{ik}_s{si}"
                                sc1, sc2, sc3, sc4, sc5 = st.columns([3, 1.5, 1.5, 2, 0.5])
                                with sc1:
                                    sig_options = [t("（手动输入）")] + signal_names
                                    sel = st.selectbox(f"  子{si+1}", sig_options, key=f"{sk}_sigsel")
                                    if sel == "（手动输入）":
                                        sub["signal"] = st.text_input("", value=sub.get("signal", ""),
                                                                      key=f"{sk}_sig", label_visibility="collapsed")
                                    else:
                                        sub["signal"] = sel
                                with sc2:
                                    sub["op"] = st.selectbox("", cmp_ops,
                                                             index=cmp_ops.index(sub.get("op", "==")),
                                                             key=f"{sk}_op", label_visibility="collapsed")
                                with sc3:
                                    sub["value"] = st.text_input("", value=str(sub.get("value", "")),
                                                                 key=f"{sk}_val", label_visibility="collapsed")
                                with sc4:
                                    sub["unit"] = st.text_input("", value=sub.get("unit", ""),
                                                                key=f"{sk}_unit", label_visibility="collapsed")
                                with sc5:
                                    if st.button("❌", key=f"{sk}_del"):
                                        item["items"].pop(si)
                                        st.rerun()
                            sa, sb = st.columns(2)
                            with sa:
                                if st.button(f"➕ 组{idx+1}加条件", key=f"{ik}_asub"):
                                    item.setdefault("items", []).append({"type": "cond", "signal": "", "op": "==", "value": "", "unit": ""})
                                    st.rerun()
                            with sb:
                                if st.button(f"🗑️ 删组{idx+1}", key=f"{ik}_dgrp"):
                                    items.pop(idx)
                                    st.rerun()
                        elif item.get("type") == "not":
                            st.markdown(f"**🚫 NOT {idx+1}**")
                            for si, sub in enumerate(item.get("items", [])):
                                sk = f"{ik}_n{si}"
                                sc1, sc2, sc3, sc4, sc5 = st.columns([3, 1.5, 1.5, 2, 0.5])
                                with sc1:
                                    sig_options = [t("（手动输入）")] + signal_names
                                    sel = st.selectbox(f"  NOT{si+1}", sig_options, key=f"{sk}_sigsel")
                                    if sel == "（手动输入）":
                                        sub["signal"] = st.text_input("", value=sub.get("signal", ""),
                                                                      key=f"{sk}_sig", label_visibility="collapsed")
                                    else:
                                        sub["signal"] = sel
                                with sc2:
                                    sub["op"] = st.selectbox("", cmp_ops,
                                                             index=cmp_ops.index(sub.get("op", "==")),
                                                             key=f"{sk}_op", label_visibility="collapsed")
                                with sc3:
                                    sub["value"] = st.text_input("", value=str(sub.get("value", "")),
                                                                 key=f"{sk}_val", label_visibility="collapsed")
                                with sc4:
                                    sub["unit"] = st.text_input("", value=sub.get("unit", ""),
                                                                key=f"{sk}_unit", label_visibility="collapsed")
                                with sc5:
                                    if st.button("❌", key=f"{sk}_del"):
                                        item["items"].pop(si)
                                        st.rerun()
                            na, nb = st.columns(2)
                            with na:
                                if st.button(f"➕ NOT{idx+1}加条件", key=f"{ik}_an"):
                                    item.setdefault("items", []).append({"type": "cond", "signal": "", "op": "==", "value": "", "unit": ""})
                                    st.rerun()
                            with nb:
                                if st.button(f"🗑️ 删NOT{idx+1}", key=f"{ik}_dn"):
                                    items.pop(idx)
                                    st.rerun()

                    sf_conditions = tree if tree.get("items") else None

                # func→signal方向：设置信号值
                sf_signal_value = ""
                if sf_dir == "func_to_signal":
                    sf_signal_value = st.text_input("设置信号值", placeholder="如: 1 表示置位, 0 表示复位", key="sf_sigval")

                sf_desc = st.text_area(t("描述"), placeholder=t("说明该关系的业务含义"), key="sf_desc")

                if st.button(t("✅ 保存关系"), type="primary", key="btn_save_sf"):
                    if sf_conditions:
                        for item in sf_conditions.get("items", []):
                            if not item.get("signal", "").strip():
                                st.error(t("存在未填写信号名的条件！"))
                                st.stop()

                    # 功能→信号：构建set_value条件
                    final_conditions = sf_conditions
                    if sf_dir == "func_to_signal" and sf_signal_value.strip():
                        final_conditions = {"type": "set_value", "value": sf_signal_value.strip()}

                    sf_rel = SignalFuncRelation(
                        project_id=current_project_id,
                        signal_id=sf_sig.id, func_id=sf_func.id,
                        direction=sf_dir, rel_type=sf_type,
                        conditions=json.dumps(final_conditions, ensure_ascii=False) if final_conditions else None,
                        description=sf_desc
                    )
                    db.add(sf_rel)
                    db.commit()
                    if "sf_cond_tree" in st.session_state:
                        st.session_state.sf_cond_tree = empty_condition()
                    notify(f"✅ 已创建: {sf_sig.name} --[{sf_type}]--> {sf_func.func_id}")
                    st.rerun()

            with sf_tab_list:
                sf_rels = db.query(SignalFuncRelation).filter_by(project_id=current_project_id).all()
                if not sf_rels:
                    st.info(t("暂无信号-功能关系。"))
                else:
                    sf_rows = []
                    for r in sf_rels:
                        s = db.query(Signal).get(r.signal_id)
                        f = db.query(Function).get(r.func_id)
                        d_label = t("信号→功能") if r.direction == "signal_to_func" else t("功能→信号")
                        cond = condition_to_text(r.conditions) if r.conditions else "-"
                        sf_rows.append({
                            "ID": r.id,
                            t("信号"): s.name if s else "?",
                            t("方向"): d_label,
                            t("关系"): r.rel_type,
                            t("功能"): f"{f.func_id} {f.name}" if f else "?",
                            t("条件"): cond[:50],
                            t("描述"): (r.description or "-")[:40]
                        })
                    st.dataframe(pd.DataFrame(sf_rows), use_container_width=True, hide_index=True)
                    st.caption(f"共 {len(sf_rows)} 条")

                    with st.expander(t("🗑️ 删除关系")):
                        sf_del = st.selectbox(t("选择要删除的关系"), sf_rels,
                                              format_func=lambda r: f"{r.id}: {db.query(Signal).get(r.signal_id).name if db.query(Signal).get(r.signal_id) else '?'} → {db.query(Function).get(r.func_id).func_id if db.query(Function).get(r.func_id) else '?'}",
                                              key="sf_del_sel")
                        if st.button(t("确认删除"), type="primary", key="sf_del_btn"):
                            target = db.query(SignalFuncRelation).get(sf_del.id)
                            if target:
                                db.delete(target)
                                db.commit()
                                notify(t("已删除"))
                                st.rerun()

    finally:
        db.close()


# ================================================================
#  📊 追溯矩阵
# ================================================================
def page_traceability():
    st.title(t("📊 功能-信号追溯矩阵"))
    render_notify()
    db = get_session()

    try:
        funcs = db.query(Function).filter_by(project_id=current_project_id).order_by(Function.func_id).all()
        if not funcs:
            st.info(t("暂无功能数据。"))
            return

        # 构建矩阵数据
        matrix_data = []
        for f in funcs:
            links = db.query(FunctionSignal).filter_by(function_id=f.id).all()
            row = {
                t("功能编号"): f.func_id,
                t("功能名称"): f.name,
                t("功能域"): f.category or "-",
                "ECU": f.module or "-",
                t("输入信号数"): sum(1 for l in links if l.direction == "Input"),
                t("输出信号数"): sum(1 for l in links if l.direction == "Output"),
                t("反馈信号数"): sum(1 for l in links if l.direction == "Feedback"),
                t("总信号数"): len(links),
                t("输入信号"): ", ".join(
                    db.query(Signal).get(l.signal_id).name for l in links if l.direction == "Input"
                ) or "-",
                t("输出信号"): ", ".join(
                    db.query(Signal).get(l.signal_id).name for l in links if l.direction == "Output"
                ) or "-",
            }
            matrix_data.append(row)

        df = pd.DataFrame(matrix_data)

        # 统计视图
        st.subheader(t("信号覆盖统计"))
        c1, c2, c3 = st.columns(3)
        with c1:
            no_input = len([r for r in matrix_data if r[t("输入信号数")] == 0])
            st.metric(t("无输入信号的功能"), no_input, delta=None if no_input == 0 else t("⚠️ 需补充"),
                      delta_color="inverse")
        with c2:
            no_output = len([r for r in matrix_data if r[t("输出信号数")] == 0])
            st.metric(t("无输出信号的功能"), no_output, delta=None if no_output == 0 else t("⚠️ 需补充"),
                      delta_color="inverse")
        with c3:
            full = len([r for r in matrix_data if r[t("总信号数")] > 0])
            st.metric(t("已关联信号的功能"), f"{full}/{len(matrix_data)}")

        st.divider()

        # 完整矩阵
        st.subheader(t("完整追溯矩阵"))
        view_mode = st.radio(t("显示模式"), ["摘要视图", "详细视图"], horizontal=True)

        if view_mode == "摘要视图":
            st.dataframe(df[[t("功能编号"), t("功能名称"), t("功能域"), "ECU",
                             t("输入信号数"), t("输出信号数"), t("反馈信号数"), t("总信号数")]],
                         use_container_width=True, hide_index=True)
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

        # CSV导出
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(t("📥 导出CSV"), csv,
                           f"追溯矩阵_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")
    finally:
        db.close()


# ================================================================
#  📥 DBC导入
# ================================================================
def parse_dbc_file(uploaded_file):
    """解析DBC文件，返回信号列表"""
    # 保存到临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix='.dbc') as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name
    
    try:
        db = cantools.database.load_file(tmp_path)
        signals = []
        
        for msg in db.messages:
            for sig in msg.signals:
                # 解析值描述
                value_desc = ""
                if sig.choices:
                    value_desc = ", ".join([f"{v}:{k}" for k, v in sig.choices.items()][:5])
                    if len(sig.choices) > 5:
                        value_desc += "..."
                
                signals.append({
                    "message_name": msg.name,
                    "message_id": f"0x{msg.frame_id:03X}",
                    "message_id_dec": msg.frame_id,
                    "dlc": msg.length,
                    "signal_name": sig.name,
                    "start_bit": sig.start,
                    "bit_length": sig.length,
                    "byte_order": "Motorola" if sig.byte_order == "big_endian" else "Intel",
                    "value_type": "Signed" if sig.is_signed else "Unsigned",
                    "factor": sig.scale,
                    "offset": sig.offset,
                    "min": safe_num(sig.minimum, float, None),
                    "max": safe_num(sig.maximum, float, None),
                    "unit": sig.unit or "",
                    "comment": safe_decode(sig.comment) if sig.comment else "",
                    "value_desc": value_desc,
                    "senders": ", ".join(msg.senders) if msg.senders else "",
                    "cycle_time": msg.cycle_time if hasattr(msg, 'cycle_time') else None,
                })
        
        return signals, db
    finally:
        os.unlink(tmp_path)


def page_dbc_import():
    st.title(t("📥 DBC文件导入"))
    render_notify()
    st.caption(t("解析对标车DBC文件，导入信号数据库用于架构分析"))
    
    db = get_session()
    
    try:
        uploaded_files = st.file_uploader(
            t("上传DBC文件（可多选）"), 
            type=['dbc'],
            accept_multiple_files=True,
            help=t("支持Vector DBC格式，可从CANdb++或CANoe导出")
        )
        
        if not uploaded_files:
            st.info(t("👆 请上传DBC文件开始解析"))
            # 删除区域（保留在页面底部供随时使用）
            with st.expander(t("🗑️ 删除导入的数据")):
                st.warning(t("⚠️ 以下操作不可恢复，请谨慎操作！"))
                total_sigs = db.query(Signal).count()
                total_rels = db.query(FuncRelation).count()
                st.markdown(f"当前数据库共有 **{total_sigs}** 个信号，**{total_rels}** 条关系")
                del_col1, del_col2 = st.columns(2)
                with del_col1:
                    if st.button(t("🗑️ 删除所有信号"), type="secondary", key="btn_del_all_sigs"):
                        st.session_state.del_confirm_sig = True
                        st.rerun()
                    if st.session_state.get("del_confirm_sig"):
                        st.error(f"确认删除全部 {total_sigs} 个信号？")
                        c_a, c_b = st.columns(2)
                        with c_a:
                            if st.button(t("✅ 确认删除"), key="btn_del_sig_confirm"):
                                try:
                                    db.query(FunctionSignal).delete()
                                    db.query(Signal).delete()
                                    db.commit()
                                    st.session_state.del_confirm_sig = False
                                    st.session_state.rel_notify = {"type": "success", "msg": t("✅ 已删除所有信号及关联关系")}
                                    st.rerun()
                                except Exception as e:
                                    db.rollback()
                                    st.error(f"删除失败: {e}")
                        with c_b:
                            if st.button(t("❌ 取消"), key="btn_del_sig_cancel"):
                                st.session_state.del_confirm_sig = False
                                st.rerun()
                with del_col2:
                    if st.button(t("🗑️ 删除所有逻辑关系"), type="secondary", key="btn_del_all_rels"):
                        st.session_state.del_confirm_rel = True
                        st.rerun()
                    if st.session_state.get("del_confirm_rel"):
                        st.error(f"确认删除全部 {total_rels} 条逻辑关系？")
                        c_a, c_b = st.columns(2)
                        with c_a:
                            if st.button(t("✅ 确认删除"), key="btn_del_rel_confirm"):
                                try:
                                    db.query(FuncRelation).delete()
                                    db.commit()
                                    st.session_state.del_confirm_rel = False
                                    st.session_state.rel_notify = {"type": "success", "msg": t("✅ 已删除所有逻辑关系")}
                                    st.rerun()
                                except Exception as e:
                                    db.rollback()
                                    st.error(f"删除失败: {e}")
                        with c_b:
                            if st.button(t("❌ 取消"), key="btn_del_rel_cancel"):
                                st.session_state.del_confirm_rel = False
                                st.rerun()
            return
            
        # 显示通知
        if "rel_notify" in st.session_state:
            n = st.session_state.rel_notify
            if n["type"] == "success":
                st.success(n["msg"])
            elif n["type"] == "error":
                st.error(n["msg"])
            if n.get("detail"):
                st.info(n["detail"])
            del st.session_state.rel_notify

        st.success(f"✅ 已上传 {len(uploaded_files)} 个DBC文件")

        # 解析所有DBC
        try:
            all_signals = []
            all_dbs = []
            for f in uploaded_files:
                sigs, db_obj = parse_dbc_file(f)
                all_signals.extend(sigs)
                all_dbs.append(db_obj)

            # 合并统计
            msg_names = set(s["message_name"] for s in all_signals)
            all_nodes = set()
            for db_obj in all_dbs:
                for n in db_obj.nodes:
                    all_nodes.add(n.name)
            col1, col2, col3, col4 = st.columns(4)
            col1.metric(t("📨 报文数量"), len(msg_names))
            col2.metric(t("📡 信号数量"), len(all_signals))
            col3.metric(t("📤 发送节点"), len(all_nodes))
            col4.metric(t("📂 DBC数量"), len(uploaded_files))

            st.divider()
            
            # 报文列表
            st.subheader(t("📨 报文列表"))
            msg_data = []
            for db_obj in all_dbs:
                for msg in db_obj.messages:
                    msg_data.append({
                        t("报文名称"): msg.name,
                        "CAN ID": f"0x{msg.frame_id:03X}",
                        "DEC ID": msg.frame_id,
                        "DLC": msg.length,
                        t("信号数"): len(msg.signals),
                        t("发送节点"): ", ".join(msg.senders) if msg.senders else "-",
                        t("周期(ms)"): msg.cycle_time if hasattr(msg, 'cycle_time') else "-",
                        t("注释"): msg.comment or "-"
                    })
            df_msg = pd.DataFrame(msg_data)
            st.dataframe(df_msg, use_container_width=True, hide_index=True)

            st.divider()
            
            # 信号列表
            st.subheader(t("📡 信号列表"))

            # 筛选条件
            c1, c2, c3 = st.columns(3)
            with c1:
                msg_filter = st.selectbox("按报文筛选", ["全部"] + sorted(list(msg_names)), key="dbc_msg_filter")
            with c2:
                unit_filter = st.selectbox("按单位筛选", ["全部"] + sorted(list(set(s["unit"] for s in all_signals if s["unit"]))), key="dbc_unit_filter")
            with c3:
                search = st.text_input("搜索信号名", key="dbc_search")

            filtered = all_signals
            if msg_filter != "全部":
                filtered = [s for s in filtered if s["message_name"] == msg_filter]
            if unit_filter != "全部":
                filtered = [s for s in filtered if s["unit"] == unit_filter]
            if search:
                filtered = [s for s in filtered if search.lower() in s["signal_name"].lower()]

            if filtered:
                df_sig = pd.DataFrame(filtered)
                st.dataframe(df_sig, use_container_width=True, hide_index=True)
                st.caption(f"共 {len(filtered)} 个信号")

            st.divider()

            # 导入选项
            st.subheader(t("📤 导入到数据库"))

            import_mode = st.radio(
                t("导入模式"),
                ["全部导入", "按报文筛选导入", "仅导入选中信号"],
                horizontal=True,
                key="dbc_import_mode"
            )

            import_list = filtered if import_mode != "全部导入" else all_signals

            if import_mode == "按报文筛选导入":
                selected_msgs = st.multiselect(
                    t("选择要导入的报文"),
                    sorted(list(msg_names)),
                    default=[msg_filter] if msg_filter != "全部" else [],
                    key="dbc_sel_msgs"
                )
                import_list = [s for s in all_signals if s["message_name"] in selected_msgs]

            # 编号前缀
            prefix = st.text_input("信号编号前缀", value="SIG-", help="导入后信号编号格式: SIG-001, SIG-002...")

            # 目标ECU选择
            ecu_options = get_config(db, "ecu_list", ["VCU", "BCM", t("ICM/仪表"), "ADDC", "GW", "CCU", "BMS", "MCU", "ESC", "EPS"]) + [t("对标车-其他")]
            target_ecu = st.selectbox(t("归属ECU"), ecu_options, index=len(ecu_options)-1, key="dbc_target_ecu")

            if st.button(t("🚀 开始导入"), type="primary", key="dbc_import_btn"):
                if not import_list:
                    st.warning(t("没有要导入的信号"))
                else:
                    existing = db.query(Signal).all()
                    existing_nums = []
                    for s in existing:
                        if s.signal_id and s.signal_id.startswith(prefix):
                            try:
                                existing_nums.append(int(s.signal_id.split("-")[-1]))
                            except:
                                pass
                    next_num = max(existing_nums) + 1 if existing_nums else 1

                    progress = st.progress(0)
                    status = st.empty()
                    imported = 0
                    skipped = 0

                    for i, sig in enumerate(import_list):
                        exists = db.query(Signal).filter_by(name=sig["signal_name"]).first()
                        if exists:
                            skipped += 1
                            continue

                        new_sig = Signal(
                            signal_id=f"{prefix}{next_num:03d}",
                            name=sig["signal_name"],
                            message_name=sig["message_name"],
                            message_id=sig["message_id"],
                            dlc=sig["dlc"],
                            start_bit=sig["start_bit"],
                            bit_length=sig["bit_length"],
                            byte_order=sig["byte_order"],
                            value_type=sig["value_type"],
                            factor=sig["factor"],
                            offset=sig["offset"],
                            min_value=sig["min"],
                            max_value=sig["max"],
                            unit=sig["unit"],
                            description=f"{sig['comment']}\n值描述: {sig['value_desc']}\n发送节点: {sig['senders']}",
                            cycle_time=sig["cycle_time"],
                            module=target_ecu
                        )
                        db.add(new_sig)
                        imported += 1
                        next_num += 1

                        progress.progress((i + 1) / len(import_list))
                        if (i + 1) % 50 == 0:
                            status.text(f"已处理 {i+1}/{len(import_list)} 个信号...")

                    db.commit()
                    progress.progress(1.0)

                    st.success(f"✅ 导入完成！新增 {imported} 个信号，跳过 {skipped} 个已存在信号")
                    st.balloons()
                    st.info(f"💡 导入后可在「信号管理」页面查看和编辑，在「功能-信号关联」页面绑定到功能")

            # ===== 删除DBC导入数据 =====
            st.divider()
            with st.expander(t("🗑️ 删除导入的数据")):
                st.warning(t("⚠️ 以下操作不可恢复，请谨慎操作！"))
                total_sigs = db.query(Signal).count()
                total_rels = db.query(FuncRelation).count()
                st.markdown(f"当前数据库共有 **{total_sigs}** 个信号，**{total_rels}** 条关系")

                del_col1, del_col2 = st.columns(2)
                with del_col1:
                    if st.button(t("🗑️ 删除所有信号"), type="secondary", key="btn_del_all_sigs"):
                        st.session_state.del_confirm_sig = True
                        st.rerun()
                    if st.session_state.get("del_confirm_sig"):
                        st.error(f"确认删除全部 {total_sigs} 个信号？")
                        c_a, c_b = st.columns(2)
                        with c_a:
                            if st.button(t("✅ 确认删除"), key="btn_del_sig_confirm"):
                                try:
                                    db.query(FunctionSignal).delete()
                                    db.query(Signal).delete()
                                    db.commit()
                                    st.session_state.del_confirm_sig = False
                                    st.session_state.rel_notify = {"type": "success", "msg": t("✅ 已删除所有信号及关联关系")}
                                    st.rerun()
                                except Exception as e:
                                    db.rollback()
                                    st.error(f"删除失败: {e}")
                        with c_b:
                            if st.button(t("❌ 取消"), key="btn_del_sig_cancel"):
                                st.session_state.del_confirm_sig = False
                                st.rerun()
                with del_col2:
                    if st.button(t("🗑️ 删除所有逻辑关系"), type="secondary", key="btn_del_all_rels"):
                        st.session_state.del_confirm_rel = True
                        st.rerun()
                    if st.session_state.get("del_confirm_rel"):
                        st.error(f"确认删除全部 {total_rels} 条逻辑关系？")
                        c_a, c_b = st.columns(2)
                        with c_a:
                            if st.button(t("✅ 确认删除"), key="btn_del_rel_confirm"):
                                try:
                                    db.query(FuncRelation).delete()
                                    db.commit()
                                    st.session_state.del_confirm_rel = False
                                    st.session_state.rel_notify = {"type": "success", "msg": t("✅ 已删除所有逻辑关系")}
                                    st.rerun()
                                except Exception as e:
                                    db.rollback()
                                    st.error(f"删除失败: {e}")
                        with c_b:
                            if st.button(t("❌ 取消"), key="btn_del_rel_cancel"):
                                st.session_state.del_confirm_rel = False
                                st.rerun()

        except Exception as e:
            st.error(f"❌ DBC解析失败: {str(e)}")
            st.code(str(e), language="python")

    finally:
        db.close()


# ================================================================
#  📤 数据导出
# ================================================================
def page_export():
    st.title(t("📤 数据导出"))
    render_notify()
    db = get_session()

    try:
        # 功能导出
        funcs = db.query(Function).filter_by(project_id=current_project_id).order_by(Function.func_id).all()
        if funcs:
            df_f = pd.DataFrame([{
                t("功能编号"): f.func_id, t("功能名称"): f.name, t("功能域"): f.category,
                "ECU": f.module, t("优先级"): f.priority, t("状态"): f.status,
                "ASIL": f.asil_level, t("描述"): f.description
            } for f in funcs])
            st.subheader(t("📋 功能清单"))
            st.dataframe(df_f, use_container_width=True, hide_index=True)
            csv_f = df_f.to_csv(index=False).encode("utf-8-sig")
            st.download_button(t("📥 导出功能清单"), csv_f, t("功能清单.csv"), "text/csv")

        st.divider()

        # 信号导出
        sigs = db.query(Signal).filter_by(project_id=current_project_id).order_by(Signal.signal_id).all()
        if sigs:
            df_s = pd.DataFrame([{
                t("信号编号"): s.signal_id, t("信号名称"): s.name, t("报文名称"): s.message_name,
                "CAN ID": s.message_id, "DLC": s.dlc, t("起始位"): s.start_bit,
                t("位长"): s.bit_length, t("精度"): s.factor, t("偏移"): s.offset,
                t("最小值"): s.min_value, t("最大值"): s.max_value, t("单位"): s.unit,
                t("字节序"): s.byte_order, t("值类型"): s.value_type, t("周期ms"): s.cycle_time,
                t("描述"): s.description
            } for s in sigs])
            st.subheader(t("📡 信号清单"))
            st.dataframe(df_s, use_container_width=True, hide_index=True)
            csv_s = df_s.to_csv(index=False).encode("utf-8-sig")
            st.download_button(t("📥 导出信号清单"), csv_s, t("信号清单.csv"), "text/csv")

        st.divider()

        # 关联导出
        links = db.query(FunctionSignal).join(Function).filter(Function.project_id == current_project_id).all()
        if links:
            rows = []
            for l in links:
                f = db.query(Function).get(l.function_id)
                s = db.query(Signal).get(l.signal_id)
                rows.append({
                    t("功能编号"): f.func_id, t("功能名称"): f.name,
                    t("信号编号"): s.signal_id, t("信号名称"): s.name,
                    t("方向"): l.direction, t("用途"): l.usage_desc, t("必需"): l.is_required
                })
            df_l = pd.DataFrame(rows)
            st.subheader(t("🔗 关联清单"))
            st.dataframe(df_l, use_container_width=True, hide_index=True)
            csv_l = df_l.to_csv(index=False).encode("utf-8-sig")
            st.download_button(t("📥 导出关联清单"), csv_l, t("关联清单.csv"), "text/csv")

        if not funcs and not sigs:
            st.info(t("暂无数据可导出。"))
    finally:
        db.close()


# ================================================================
#  ⚙️ 配置管理
# ================================================================
def page_config():
    st.title(t("⚙️ 配置管理"))

    render_notify()
    st.caption(t("管理ECU列表、功能域等下拉选项，修改后全局生效"))
    db = get_session()

    config_items = {
        "ecu_list": (t("归属ECU列表"), t("VCU / BCM / ICM / ADDC / GW 等")),
        "category_list": (t("功能域列表"), t("车身 / 动力 / 底盘 / 座舱 等")),
        "priority_list": (t("优先级列表"), "High / Medium / Low"),
        "status_list": (t("状态列表"), "Draft / Review / Approved / Released"),
        "asil_list": (t("ASIL等级列表"), "- / QM / ASIL-A / ASIL-B / ASIL-C / ASIL-D"),
    }

    try:
        for cfg_key, (label, hint) in config_items.items():
            with st.expander(f"📝 {label}", expanded=(cfg_key == "ecu_list")):
                current = get_config(db, cfg_key, [])
                st.caption(f"当前选项：{' / '.join(current)}")
                st.caption(f"💡 提示：{hint}")

                col_input, col_add = st.columns([4, 1])
                with col_input:
                    new_item = st.text_input(
                        f"添加新{label}",
                        placeholder=t("输入新选项名称"),
                        key=f"cfg_add_{cfg_key}"
                    )
                with col_add:
                    st.write("")
                    st.write("")
                    if st.button(t("➕ 添加"), key=f"cfg_btn_add_{cfg_key}"):
                        new_item = new_item.strip()
                        if not new_item:
                            st.warning(t("名称不能为空"))
                        elif new_item in current:
                            st.warning(f"「{new_item}」已存在")
                        else:
                            current.append(new_item)
                            set_config(db, cfg_key, current)
                            notify(f"已添加「{new_item}」")

                            st.rerun()

            # 删除列表
                if current:
                    st.markdown(t("**当前选项（点击删除）：**"))
                # 每行显示，带删除按钮
                    for i, item in enumerate(current):
                        col_name, col_del = st.columns([5, 1])
                        with col_name:
                            st.write(f"  {i+1}. {item}")
                        with col_del:
                            if st.button("🗑️", key=f"cfg_del_{cfg_key}_{i}"):
                                removed = current.pop(i)
                                set_config(db, cfg_key, current)
                                notify(f"已删除「{removed}」")

                                st.rerun()

    # 重置为默认值
        st.divider()
        with st.expander(t("⚠️ 重置为默认值")):
                st.warning(t("将恢复所有配置项为系统默认值，自定义的选项会丢失！"))
                reset_key = st.selectbox(t("选择要重置的配置"),
                                      [k for k in config_items],
                                      format_func=lambda k: config_items[k][0],
                                      key="cfg_reset_sel")
                if st.button(t("🔄 确认重置"), type="primary", key="cfg_reset_btn"):
                    defaults = {
                        "ecu_list": ["VCU", "BCM", t("ICM/仪表"), "ADDC", "GW", "CCU", "BMS", "MCU", "ESC", "EPS", t("其他")],
                        "category_list": [t("车身"), t("动力"), t("底盘"), t("座舱"), t("热管理"), "ADAS", t("网关"), t("充电"), t("其他")],
                        "priority_list": ["High", "Medium", "Low"],
                        "status_list": ["Draft", "Review", "Approved", "Released"],
                        "asil_list": ["-", "QM", "ASIL-A", "ASIL-B", "ASIL-C", "ASIL-D"],
                    }
                    set_config(db, reset_key, defaults[reset_key])
                    notify(f"已重置「{config_items[reset_key][0]}」为默认值")

                    st.rerun()

    finally:
        db.close()


# ========== 借用数据辅助函数 ==========
def _borrow_data(db, src_project_id, dst_project_id):
    """将源车型的功能、信号、关系复制到目标车型（跳过已存在的）"""
    db.autoflush = False  # 关闭自动flush，避免大批量插入时冲突
    try:

        # 借用功能
        src_funcs = db.query(Function).filter_by(project_id=src_project_id).all()
        id_map = {}
        for f in src_funcs:
            existing = db.query(Function).filter_by(
                func_id=f.func_id, project_id=dst_project_id
            ).first()
            if existing:
                id_map[f.id] = existing.id
                continue
            new_f = Function(
                project_id=dst_project_id, name=f.name, func_id=f.func_id,
                category=f.category, module=f.module, description=f.description,
                priority=f.priority, status=f.status, asil_level=f.asil_level,
                source_project_id=src_project_id
            )
            db.add(new_f)
            db.flush()
            id_map[f.id] = new_f.id

        # 借用信号
        src_sigs = db.query(Signal).filter_by(project_id=src_project_id).all()
        for s in src_sigs:
            existing = db.query(Signal).filter_by(
                signal_id=s.signal_id, project_id=dst_project_id
            ).first()
            if existing:
                continue
            new_s = Signal(
                project_id=dst_project_id, name=s.name, signal_id=s.signal_id,
                message_name=s.message_name, message_id=s.message_id,
                dlc=s.dlc, start_bit=s.start_bit, bit_length=s.bit_length,
                factor=s.factor, offset=s.offset, min_value=s.min_value,
                max_value=s.max_value, unit=s.unit, byte_order=s.byte_order,
                value_type=s.value_type, cycle_time=s.cycle_time,
                module=s.module, description=s.description,
                source_project_id=src_project_id
            )
            db.add(new_s)

        # 借用逻辑关系
        src_rels = db.query(FuncRelation).filter_by(project_id=src_project_id).all()
        for r in src_rels:
            new_src_id = id_map.get(r.source_id)
            new_tgt_id = id_map.get(r.target_id)
            if new_src_id and new_tgt_id:
                existing = db.query(FuncRelation).filter_by(
                    project_id=dst_project_id, source_id=new_src_id,
                    target_id=new_tgt_id, rel_type=r.rel_type
                ).first()
                if existing:
                    continue
                new_r = FuncRelation(
                    project_id=dst_project_id, source_id=new_src_id,
                    target_id=new_tgt_id, rel_type=r.rel_type,
                    description=r.description, conditions=r.conditions,
                    source_project_id=src_project_id
                )
                db.add(new_r)

        db.commit()
    finally:
        db.autoflush = True  # 恢复


# ================================================================
#  🚘 车型管理
# ================================================================
def page_project():
    st.title(t("🚘 车型管理"))

    render_notify()
    st.caption(t("管理不同车型项目，支持差异化配置和数据借用"))
    db = get_session()

    try:
        tab_list, tab_add, tab_borrow = st.tabs(["📋 车型列表", "➕ 新建车型", "📥 借用数据"])

        with tab_list:
            projects = db.query(Project).order_by(Project.id).all()
            if not projects:
                st.info(t("暂无车型。"))
            else:
                rows = []
                for p in projects:
                    func_cnt = db.query(Function).filter_by(project_id=p.id).count()
                    sig_cnt = db.query(Signal).filter_by(project_id=p.id).count()
                    rel_cnt = db.query(FuncRelation).filter_by(project_id=p.id).count()
                    base_name = db.query(Project).get(p.base_project_id).name if p.base_project_id else "-"
                    rows.append({
                        "ID": p.id,
                        t("车型名称"): p.name,
                        t("车型代码"): p.code or "-",
                        t("功能数"): func_cnt,
                        t("信号数"): sig_cnt,
                        t("关系数"): rel_cnt,
                        t("借用来源"): base_name,
                        t("描述"): (p.description or "-")[:40]
                    })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # 删除车型
            with st.expander(t("🗑️ 删除车型")):
                st.warning(t("删除车型会同时删除该车型下的所有功能、信号和关系数据！"))
                del_projects = [p for p in projects if p.name != "通用"]
                if del_projects:
                    del_sel = st.selectbox(t("选择要删除的车型"), del_projects,
                                           format_func=lambda p: f"{p.name} ({p.code or '-'})",
                                           key="del_project")
                    if st.button(t("确认删除"), type="primary", key="del_proj_btn"):
                        deleted_name = del_sel.name
                        deleted_id = del_sel.id
                        # 用当前session重新获取目标
                        target = db.query(Project).get(deleted_id)
                        # 删除关联数据
                        db.query(FuncRelation).filter_by(project_id=deleted_id).delete()
                        db.query(FunctionSignal).filter(FunctionSignal.function_id.in_(
                            db.query(Function.id).filter_by(project_id=deleted_id)
                        )).delete(synchronize_session='fetch')
                        db.query(Function).filter_by(project_id=deleted_id).delete()
                        db.query(Signal).filter_by(project_id=deleted_id).delete()
                        db.delete(target)
                        db.commit()
                        notify(f"已删除车型 {deleted_name}")

                        st.rerun()
                else:
                    st.caption(t("「通用」车型不可删除"))

        with tab_add:
            with st.form("add_project"):
                st.subheader(t("新建车型项目"))
                c1, c2 = st.columns(2)
                with c1:
                    pname = st.text_input("车型名称 *", placeholder="如: MEV02")
                    pcode = st.text_input("车型代码", placeholder="如: MEV02-A")
                with c2:
                    base_opts = db.query(Project).all()
                    base_sel = st.selectbox(t("从现有车型借用数据（可选）"),
                                            [t("不借用")] + [p.name for p in base_opts],
                                            key="base_proj")
                pdesc = st.text_area(t("车型描述"), placeholder=t("简要描述该车型的特点和目标"))

                if st.form_submit_button(t("✅ 创建车型"), type="primary"):
                    if not pname:
                        st.error(t("车型名称不能为空"))
                    elif db.query(Project).filter_by(name=pname).first():
                        st.error(f"车型「{pname}」已存在")
                    else:
                        base_id = None
                        if base_sel != "不借用":
                            base_proj = db.query(Project).filter_by(name=base_sel).first()
                            if base_proj:
                                base_id = base_proj.id

                        new_proj = Project(
                            name=pname, code=pcode, description=pdesc,
                            base_project_id=base_id
                        )
                        db.add(new_proj)
                        db.commit()

                        # 如果选择了借用，复制数据
                        if base_id:
                            _borrow_data(db, base_id, new_proj.id)
                            st.success(f"✅ 车型「{pname}」已创建，已从「{base_sel}」借用数据")
                        else:
                            notify(f"✅ 车型「{pname}」已创建（空项目）")

                            st.rerun()

        with tab_borrow:
            st.subheader(t("从其他车型借用功能和信号"))
            st.caption(t("将其他车型的功能和信号复制到当前车型，修改不会互相影响"))

            # 通知显示
            if "rel_notify" in st.session_state:
                n = st.session_state.rel_notify
                if n["type"] == "success":
                    st.success(n["msg"])
                elif n["type"] == "error":
                    st.error(n["msg"])
                del st.session_state.rel_notify

            src_projects = db.query(Project).filter(Project.id != current_project_id).all()
            if not src_projects:
                st.info(t("没有其他车型可以借用。请先创建新车型。"))
            else:
                src_proj = st.selectbox(t("选择来源车型"), src_projects,
                                    format_func=lambda p: f"{p.name} ({p.code or '-'})",
                                    key="borrow_src")

                if src_proj:
                    # 显示可借用的数据
                    src_funcs = db.query(Function).filter_by(project_id=src_proj.id).all()
                    src_sigs = db.query(Signal).filter_by(project_id=src_proj.id).all()

                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric(t("可借用功能"), len(src_funcs))
                    with col2:
                        st.metric(t("可借用信号"), len(src_sigs))

                    borrow_what = st.multiselect("选择要借用的数据类型",
                                                  ["功能", "信号", "逻辑关系"],
                                                  default=["功能", "信号", "逻辑关系"])

                    if st.button(t("📥 执行借用"), type="primary", key="btn_borrow"):
                        borrowed = {t("功能"): 0, t("信号"): 0, t("关系"): 0}

                        # 借用功能
                        if "功能" in borrow_what:
                            for f in src_funcs:
                                existing = db.query(Function).filter_by(
                                    func_id=f.func_id, project_id=current_project_id
                                ).first()
                                if not existing:
                                    new_f = Function(
                                        project_id=current_project_id,
                                        name=f.name, func_id=f.func_id,
                                        category=f.category, module=f.module,
                                        description=f.description, priority=f.priority,
                                        status=f.status, asil_level=f.asil_level,
                                        source_project_id=src_proj.id
                                    )
                                    db.add(new_f)
                                    borrowed[t("功能")] += 1

                        # 借用信号
                        if "信号" in borrow_what:
                            for s in src_sigs:
                                existing = db.query(Signal).filter_by(
                                    signal_id=s.signal_id, project_id=current_project_id
                                ).first()
                                if not existing:
                                    new_s = Signal(
                                        project_id=current_project_id,
                                        name=s.name, signal_id=s.signal_id,
                                        message_name=s.message_name, message_id=s.message_id,
                                        dlc=s.dlc, start_bit=s.start_bit, bit_length=s.bit_length,
                                        factor=s.factor, offset=s.offset,
                                        min_value=s.min_value, max_value=s.max_value,
                                        unit=s.unit, byte_order=s.byte_order,
                                        value_type=s.value_type, cycle_time=s.cycle_time,
                                        module=s.module, description=s.description,
                                        source_project_id=src_proj.id
                                    )
                                    db.add(new_s)
                                    borrowed[t("信号")] += 1

                        # 借用逻辑关系
                        if "逻辑关系" in borrow_what:
                            src_rels = db.query(FuncRelation).filter_by(project_id=src_proj.id).all()
                            for r in src_rels:
                                # 找到当前车型中对应的源和目标功能
                                src_f = db.query(Function).filter_by(project_id=src_proj.id, id=r.source_id).first()
                                tgt_f = db.query(Function).filter_by(project_id=src_proj.id, id=r.target_id).first()
                                if src_f and tgt_f:
                                    new_src = db.query(Function).filter_by(
                                        func_id=src_f.func_id, project_id=current_project_id
                                    ).first()
                                    new_tgt = db.query(Function).filter_by(
                                        func_id=tgt_f.func_id, project_id=current_project_id
                                    ).first()
                                    if new_src and new_tgt:
                                        new_r = FuncRelation(
                                            project_id=current_project_id,
                                            source_id=new_src.id, target_id=new_tgt.id,
                                            rel_type=r.rel_type, description=r.description,
                                            conditions=r.conditions,
                                            source_project_id=src_proj.id
                                        )
                                        db.add(new_r)
                                        borrowed[t("关系")] += 1

                        db.commit()
                        st.session_state.rel_notify = {
                            "type": "success",
                            "msg": f"✅ 借用完成！功能 +{borrowed[t('功能')]}，信号 +{borrowed[t('信号')]}，关系 +{borrowed[t('关系')]}"
                        }
                        st.rerun()

    finally:
        db.close()


# ================================================================
# ================================================================
#  📥 Excel通讯矩阵解析
# ================================================================
def page_excel_import():
    st.title(t("📥 Excel通讯矩阵解析"))
    st.caption(t("解析通讯协议Excel中的s/r矩阵，自动推导ECU间信号收发关系"))
    db = get_session()

    try:
        # 初始化session state
        if "excel_parsed_data" not in st.session_state:
            st.session_state.excel_parsed_data = None
        if "import_sig_msg" not in st.session_state:
            st.session_state.import_sig_msg = ""
        if "import_rel_msg" not in st.session_state:
            st.session_state.import_rel_msg = ""

        # 文件上传
        uploaded_file = st.file_uploader(
            t("上传通讯矩阵Excel文件"),
            type=["xlsx", "xls"],
            key="excel_uploader"
        )

        if uploaded_file is None:
            return

        # 通知显示
        if "rel_notify" in st.session_state:
            n = st.session_state.rel_notify
            if n["type"] == "success":
                st.success(n["msg"])
            elif n["type"] == "error":
                st.error(n["msg"])
            if n.get("detail"):
                st.info(n["detail"])
            del st.session_state.rel_notify

        st.success(f"✅ 文件已上传: {uploaded_file.name} ({uploaded_file.size/1024:.1f} KB)")

        # 临时保存到本地
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name

        wb = openpyxl.load_workbook(tmp_path, data_only=True)
        data_sheets = [s for s in wb.sheetnames if s not in ("History", "Legend", "RoutingTable", "Extra")]

        selected_sheets = st.multiselect(
            t("选择要解析的Sheet"), data_sheets,
            default=data_sheets, key="excel_sheets"
        )

        # 解析按钮
        if st.button(t("🔍 解析通讯矩阵"), type="primary", key="btn_parse_excel"):
            if not selected_sheets:
                st.warning(t("请至少选择一个Sheet"))
            else:
                with st.spinner(t("正在解析通讯矩阵...")):
                    all_results = {}
                    for sheet_name in selected_sheets:
                        ws = wb[sheet_name]

                        # 解析ECU列（列29+）
                        ecu_cols = {}
                        for col in range(29, ws.max_column + 1):
                            val = ws.cell(row=1, column=col).value
                            if val:
                                clean_name = str(val).strip().replace("\r\n", "\n").replace("\r", "\n").split("\n")[0].strip()
                                if clean_name and clean_name not in ("Bus Load", "Reserve", "Reserve1"):
                                    ecu_cols[col] = clean_name

                        if not ecu_cols:
                            st.warning(f"Sheet「{sheet_name}」未找到ECU列（列29+）")
                            continue

                        # 解析报文和信号
                        messages = []
                        current_msg = None
                        for row_idx in range(2, ws.max_row + 1):
                            msg_name = ws.cell(row=row_idx, column=1).value
                            sig_name_raw = ws.cell(row=row_idx, column=7).value

                            if msg_name:
                                msg_name = str(msg_name).strip()
                                msg_id = ws.cell(row=row_idx, column=3).value
                                dlc = ws.cell(row=row_idx, column=6).value
                                cycle = ws.cell(row=row_idx, column=5).value
                                current_msg = {
                                    "name": msg_name,
                                    "id": str(msg_id).strip() if msg_id else "",
                                    "dlc": dlc,
                                    "cycle": cycle,
                                    "senders": set(),
                                    "receivers": set(),
                                    "signals": []
                                }

                                # 报文行解析s/r
                                for col, ecu_name in ecu_cols.items():
                                    val = ws.cell(row=row_idx, column=col).value
                                    if val:
                                        val_str = str(val).strip().lower()
                                        if val_str == "s":
                                            current_msg["senders"].add(ecu_name)
                                        elif val_str == "r":
                                            current_msg["receivers"].add(ecu_name)

                                messages.append(current_msg)

                            if sig_name_raw:
                                sig_name = str(sig_name_raw).strip()
                                if current_msg:
                                    current_msg["signals"].append(sig_name)

                                # 信号行也检查s/r（有的Excel在信号行标记）
                                if current_msg:
                                    for col, ecu_name in ecu_cols.items():
                                        val = ws.cell(row=row_idx, column=col).value
                                        if val:
                                            val_str = str(val).strip().lower()
                                            if val_str == "s":
                                                current_msg["senders"].add(ecu_name)
                                            elif val_str == "r":
                                                current_msg["receivers"].add(ecu_name)

                        all_results[sheet_name] = {
                            "messages": messages,
                            "ecu_cols": ecu_cols
                        }

                # 缓存到session state
                st.session_state.excel_parsed_data = all_results
                st.session_state.excel_sheets_selected = selected_sheets
                st.rerun()

        # 从session state读取已解析的数据
        if st.session_state.excel_parsed_data is not None:
            all_results = st.session_state.excel_parsed_data

            # ECU汇总
            all_ecus = set()
            for sheet_name, result in all_results.items():
                for col, ecu in result["ecu_cols"].items():
                    all_ecus.add(ecu)

            # ========== 构建信号级数据 ==========
            signal_flow = []
            ecu_send = {}
            ecu_recv = {}
            pair_signals = {}

            for sheet_name, result in all_results.items():
                for msg in result["messages"]:
                    senders = msg["senders"]
                    receivers = msg["receivers"]
                    for sig_name in msg.get("signals", []):
                        for sender in senders:
                            for receiver in receivers:
                                if sender != receiver:
                                    signal_flow.append({
                                        t("信号名"): sig_name,
                                        t("报文名"): msg["name"],
                                        "CAN ID": msg["id"],
                                        "Sheet": sheet_name,
                                        t("发送ECU"): sender,
                                        t("接收ECU"): receiver,
                                    })
                                    ecu_send.setdefault(sender, {}).setdefault(receiver, []).append(sig_name)
                                    ecu_recv.setdefault(receiver, {}).setdefault(sender, []).append(sig_name)
                                    pair_signals.setdefault((sender, receiver), set()).add(sig_name)

            st.success(f"✅ 解析完成：{sum(len(r['messages']) for r in all_results.values())} 个报文，"
                       f"{len(all_ecus)} 个ECU节点，{len(signal_flow)} 条信号收发关系")

            # ECU列表
            st.markdown(f"**ECU节点：** {', '.join(sorted(all_ecus))}")

            if signal_flow:
                # ====== 1. ECU信号收发总览 ======
                st.subheader(t("📊 ECU信号收发总览"))
                selected_ecu = st.selectbox(t("选择ECU查看详情"), sorted(all_ecus), key="ecu_selector")

                if selected_ecu in ecu_send or selected_ecu in ecu_recv:
                    col_a, col_b = st.columns(2)
                    with col_a:
                        sends = ecu_send.get(selected_ecu, {})
                        total_send = sum(len(sigs) for sigs in sends.values())
                        st.metric(t("📤 发出信号"), total_send, help=f"共发给 {len(sends)} 个ECU")
                        if sends:
                            send_rows = []
                            for rx_ecu, sigs in sorted(sends.items(), key=lambda x: -len(x[1])):
                                send_rows.append({
                                    t("接收ECU"): rx_ecu,
                                    t("信号数"): len(sigs),
                                    t("信号列表"): ", ".join(sigs)
                                })
                            st.dataframe(pd.DataFrame(send_rows),
                                         column_config={t("信号列表"): st.column_config.TextColumn(width="large")},
                                         use_container_width=True, hide_index=True)
                        else:
                            st.info(t("该ECU无发出信号"))

                    with col_b:
                        recvs = ecu_recv.get(selected_ecu, {})
                        total_recv = sum(len(sigs) for sigs in recvs.values())
                        st.metric(t("📥 接收信号"), total_recv, help=f"共从 {len(recvs)} 个ECU接收")
                        if recvs:
                            recv_rows = []
                            for tx_ecu, sigs in sorted(recvs.items(), key=lambda x: -len(x[1])):
                                recv_rows.append({
                                    t("发送ECU"): tx_ecu,
                                    t("信号数"): len(sigs),
                                    t("信号列表"): ", ".join(sigs)
                                })
                            st.dataframe(pd.DataFrame(recv_rows),
                                         column_config={t("信号列表"): st.column_config.TextColumn(width="large")},
                                         use_container_width=True, hide_index=True)
                        else:
                            st.info(t("该ECU无接收信号"))

                # ====== 2. ECU间信号级汇总 ======
                st.subheader(t("🔗 ECU间信号级汇总"))
                pair_rows = []
                for (tx, rx), sig_set in sorted(pair_signals.items(), key=lambda x: -len(x[1])):
                    sorted_sigs = sorted(sig_set)
                    pair_rows.append({
                        t("发送ECU"): tx,
                        t("接收ECU"): rx,
                        t("信号数"): len(sorted_sigs),
                        t("信号列表"): ", ".join(sorted_sigs[:8]) + ("..." if len(sorted_sigs) > 8 else "")
                    })
                st.dataframe(pd.DataFrame(pair_rows),
                             column_config={t("信号列表"): st.column_config.TextColumn(width="large")},
                             use_container_width=True, hide_index=True)

                # ====== 3. 网络图 ======
                st.subheader(t("📊 ECU信号流网络图"))
                ecu_colors = {
                    "VCU": "#FF5722", "BCM": "#4CAF50", "IVI": "#9C27B0",
                    "MCU": "#3F51B5", "BMS": "#E91E63", "A3in1": "#00BCD4",
                    "ABS": "#FF9800", "ACU": "#795548", "EVCC": "#607D8B",
                    "SS": "#009688", "AVAS": "#CDDC39", "AL_FL": "#E91E63",
                    "AL_FR": "#E91E63", "AL_RL": "#E91E63", "AL_RR": "#E91E63",
                    "EAC": "#2196F3", "EPS": "#8BC34A"
                }

                graph_nodes = []
                graph_edges = []
                for ecu in sorted(all_ecus):
                    color = ecu_colors.get(ecu, "#757575")
                    send_cnt = sum(len(v) for v in ecu_send.get(ecu, {}).values())
                    recv_cnt = sum(len(v) for v in ecu_recv.get(ecu, {}).values())
                    graph_nodes.append({
                        "id": ecu, "label": ecu,
                        "title": f"发出: {send_cnt}信号 | 接收: {recv_cnt}信号",
                        "color": {"background": color, "border": color},
                        "font": {"color": "#fff", "size": 14, "face": "Microsoft YaHei"},
                        "shape": "dot", "size": max(20, min(50, (send_cnt + recv_cnt) * 2))
                    })

                for (tx, rx), sig_set in sorted(pair_signals.items(), key=lambda x: -len(x[1])):
                    sorted_sigs = sorted(sig_set)
                    graph_edges.append({
                        "from": tx, "to": rx,
                        "label": f"{len(sorted_sigs)}信号",
                        "title": f"信号数: {len(sorted_sigs)}\n信号: {', '.join(sorted_sigs[:10])}\n...",
                        "color": {"color": "#4FC3F7"},
                        "font": {"size": 10, "align": "middle", "face": "Microsoft YaHei"},
                        "arrows": "to",
                        "width": max(1, min(8, len(sorted_sigs) // 2)),
                        "smooth": {"type": "cubicBezier"}
                    })

                graph_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body{{margin:0;background:#1a1a2e;overflow:hidden}}#g{{width:100%;height:100vh}}</style>
</head><body><div id="g"></div>
<script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"></script>
<script>
var nodes=new vis.DataSet({json.dumps(graph_nodes, ensure_ascii=False)});
var edges=new vis.DataSet({json.dumps(graph_edges, ensure_ascii=False)});
new vis.Network(document.getElementById('g'),{{nodes:nodes,edges:edges}},{{physics:{{solver:'forceAtlas2Based',forceAtlas2Based:{{gravitationalConstant:-200,centralGravity:0.01,springLength:250,springConstant:0.02}},stabilization:{{iterations:100}}}},interaction:{{hover:true}}}});
</script></body></html>"""
                components.html(graph_html, height=500, scrolling=False)

                # ====== 4. 导入信号到当前车型 ======
                st.divider()
                st.subheader(t("📥 导入到当前车型数据库"))

                # 导入结果显示区
                if st.session_state.import_sig_msg:
                    if st.session_state.import_sig_msg.startswith("✅"):
                        st.success(st.session_state.import_sig_msg)
                    else:
                        st.error(st.session_state.import_sig_msg)
                if st.session_state.import_rel_msg:
                    if st.session_state.import_rel_msg.startswith("✅"):
                        st.success(st.session_state.import_rel_msg)
                    else:
                        st.error(st.session_state.import_rel_msg)

                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button(t("📥 导入信号到当前车型"), type="primary", key="btn_import_excel_sigs"):
                        new_count = 0
                        skip_count = 0
                        errors = []
                        for sheet_name, result in all_results.items():
                            for msg in result["messages"]:
                                for sig_name in msg.get("signals", []):
                                    try:
                                        existing = db.query(Signal).filter_by(
                                            name=sig_name, project_id=current_project_id
                                        ).first()
                                        if not existing:
                                            senders = list(msg["senders"])
                                            new_sig = Signal(
                                                project_id=current_project_id,
                                                name=sig_name, signal_id=sig_name,
                                                message_name=msg["name"],
                                                message_id=msg["id"],
                                                dlc=msg.get("dlc"),
                                                cycle_time=msg.get("cycle"),
                                                module=senders[0] if senders else "",
                                                description=t("从通讯矩阵Excel导入")
                                            )
                                            db.add(new_sig)
                                            new_count += 1
                                        else:
                                            skip_count += 1
                                    except Exception as e:
                                        errors.append(f"{sig_name}: {str(e)}")

                        try:
                            db.commit()
                            msg_parts = [f"✅ 导入完成：新增 {new_count} 个信号"]
                            if skip_count > 0:
                                msg_parts.append(f"，跳过 {skip_count} 个已存在信号")
                            if errors:
                                msg_parts.append(f"，{len(errors)} 个导入失败")
                            final_msg = "".join(msg_parts)
                            st.session_state.import_sig_msg = final_msg
                            if errors:
                                st.session_state.import_sig_msg += t("\n失败详情: ") + "; ".join(errors[:5])
                        except Exception as e:
                            db.rollback()
                            st.session_state.import_sig_msg = f"❌ 导入失败: {str(e)}"
                        st.rerun()

                with col_b:
                    if st.button(t("📥 导入ECU关系到当前车型"), type="primary", key="btn_import_excel_rels"):
                        new_count = 0
                        skip_count = 0
                        errors = []
                        for (tx, rx), sig_set in pair_signals.items():
                            try:
                                src_func = db.query(Function).filter_by(
                                    project_id=current_project_id, module=tx
                                ).first()
                                tgt_func = db.query(Function).filter_by(
                                    project_id=current_project_id, module=rx
                                ).first()
                                if src_func and tgt_func:
                                    existing = db.query(FuncRelation).filter_by(
                                        project_id=current_project_id,
                                        source_id=src_func.id, target_id=tgt_func.id,
                                        rel_type=t("数据流")
                                    ).first()
                                    if not existing:
                                        sorted_sigs = sorted(sig_set)
                                        rel = FuncRelation(
                                            project_id=current_project_id,
                                            source_id=src_func.id, target_id=tgt_func.id,
                                            rel_type=t("数据流"),
                                            description=f"[Excel] {tx}→{rx}: {len(sorted_sigs)}信号({', '.join(sorted_sigs[:5])})",
                                            conditions=json.dumps({"op": "AND", "items": [
                                                {"type": "cond", "signal": s, "op": "==", "value": "1", "unit": "", "ecu": tx}
                                                for s in sorted_sigs[:3]
                                            ]}, ensure_ascii=False)
                                        )
                                        db.add(rel)
                                        new_count += 1
                                    else:
                                        skip_count += 1
                                else:
                                    skip_count += 1
                                    if not src_func:
                                        errors.append(f"ECU「{tx}」在功能管理中不存在")
                                    if not tgt_func:
                                        errors.append(f"ECU「{rx}」在功能管理中不存在")
                            except Exception as e:
                                errors.append(f"{tx}→{rx}: {str(e)}")

                        try:
                            db.commit()
                            msg_parts = [f"✅ 导入完成：新增 {new_count} 条关系"]
                            if skip_count > 0:
                                msg_parts.append(f"，跳过 {skip_count} 条")
                            if errors:
                                msg_parts.append(f"，{len(errors)} 个问题")
                            final_msg = "".join(msg_parts)
                            if errors:
                                final_msg += "\n⚠️ " + "; ".join(errors[:5])
                            st.session_state.import_rel_msg = final_msg
                        except Exception as e:
                            db.rollback()
                            st.session_state.import_rel_msg = f"❌ 导入失败: {str(e)}"
                        st.rerun()

                # ====== 5. 详细信号收发表 ======
                with st.expander(t("📋 信号级收发详情")):
                    st.dataframe(pd.DataFrame(signal_flow), use_container_width=True, hide_index=True)

                # ====== 6. 删除导入的数据 ======
                st.divider()
                with st.expander(t("🗑️ 删除导入的数据")):
                    st.warning(t("⚠️ 以下操作不可恢复，请谨慎操作！"))
                    total_sigs = db.query(Signal).count()
                    total_rels = db.query(FuncRelation).count()
                    st.markdown(f"当前数据库共有 **{total_sigs}** 个信号，**{total_rels}** 条关系")

                    del_col1, del_col2 = st.columns(2)
                    with del_col1:
                        if st.button(t("🗑️ 删除所有信号"), type="secondary", key="btn_excel_del_sigs"):
                            st.session_state.del_confirm_sig = True
                            st.rerun()
                        if st.session_state.get("del_confirm_sig"):
                            st.error(f"确认删除全部 {total_sigs} 个信号？")
                            c_a, c_b = st.columns(2)
                            with c_a:
                                if st.button(t("✅ 确认删除"), key="btn_excel_del_sig_ok"):
                                    try:
                                        db.query(FunctionSignal).delete()
                                        db.query(Signal).delete()
                                        db.commit()
                                        st.session_state.del_confirm_sig = False
                                        st.session_state.rel_notify = {
                                            "type": "success",
                                            "msg": t("✅ 已删除所有信号及关联关系")
                                        }
                                        st.rerun()
                                    except Exception as e:
                                        db.rollback()
                                        st.error(f"删除失败: {e}")
                            with c_b:
                                if st.button(t("❌ 取消"), key="btn_excel_del_sig_no"):
                                    st.session_state.del_confirm_sig = False
                                    st.rerun()

                    with del_col2:
                        if st.button(t("🗑️ 删除所有逻辑关系"), type="secondary", key="btn_excel_del_rels"):
                            st.session_state.del_confirm_rel = True
                            st.rerun()
                        if st.session_state.get("del_confirm_rel"):
                            st.error(f"确认删除全部 {total_rels} 条逻辑关系？")
                            c_a, c_b = st.columns(2)
                            with c_a:
                                if st.button(t("✅ 确认删除"), key="btn_excel_del_rel_ok"):
                                    try:
                                        db.query(FuncRelation).delete()
                                        db.commit()
                                        st.session_state.del_confirm_rel = False
                                        st.session_state.rel_notify = {
                                            "type": "success",
                                            "msg": t("✅ 已删除所有逻辑关系")
                                        }
                                        st.rerun()
                                    except Exception as e:
                                        db.rollback()
                                        st.error(f"删除失败: {e}")
                            with c_b:
                                if st.button(t("❌ 取消"), key="btn_excel_del_rel_no"):
                                    st.session_state.del_confirm_rel = False
                                    st.rerun()

    finally:
        db.close()

# ========== 页面路由 ==========
PAGES = {
    "📊 总览仪表盘": page_dashboard,
    "📋 功能管理": page_functions,
    "📡 信号管理": page_signals,
    "📥 DBC导入": page_dbc_import,
    "📥 Excel通讯矩阵": page_excel_import,
    "🔗 功能-信号关联": page_func_signal,
    "🔄 逻辑关系": page_relations,
    "📊 追溯矩阵": page_traceability,
    "📤 数据导出": page_export,
    "🚘 车型管理": page_project,
    "⚙️ 配置管理": page_config,
}

PAGES[page]()
