"""Knowledge and review workspace for automotive requirements engineering."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from automotive_knowledge import (
    LOCAL_REFERENCE_PATH,
    REQUIREMENT_TEMPLATES,
    STANDARDS_CATALOG,
    TRACEABILITY_BLUEPRINTS,
    UPSTREAM_COMMIT,
    UPSTREAM_REPOSITORY,
    assess_requirement_quality,
    quality_summary,
)
from db import Requirement, SessionLocal, TraceLink


def _render_findings(result: dict):
    c1, c2, c3 = st.columns(3)
    c1.metric("质量得分", f"{result['score']}/100")
    c2.metric("等级", result["grade"])
    c3.metric("评审门禁", "可提交" if result["ready_for_review"] else "需完善")
    findings = result["findings"]
    if not findings:
        st.success("未发现规则性问题。仍需由领域专家确认技术正确性和标准适用性。")
        return
    st.dataframe(pd.DataFrame([{
        "级别": item["severity"],
        "规则": item["code"],
        "发现": item["message"],
        "建议": item["suggestion"],
    } for item in findings]), use_container_width=True, hide_index=True)


def page_requirements_knowledge(project_id: int):
    st.markdown(
        '<div class="ee-kicker">KNOWLEDGE / 质量工程</div>'
        '<div class="ee-title">汽车需求知识与评审</div>'
        '<div class="ee-subtitle">把需求模板、质量门禁、ASPICE/功能安全追踪模式和标准适用边界放进同一个工程工作台。</div>',
        unsafe_allow_html=True,
    )
    st.warning(
        "此工作台用于工程辅助和评审准备，不构成 ISO 26262、Automotive SPICE、SOTIF "
        "或中国法规的合规认证。正式项目应使用授权标准文本和组织流程。",
        icon="⚠️",
    )

    db = SessionLocal()
    try:
        requirements = db.query(Requirement).filter_by(project_id=project_id).order_by(Requirement.req_id).all()
        links = db.query(TraceLink).filter_by(project_id=project_id).all()
        tab_gate, tab_review, tab_templates, tab_standards, tab_source = st.tabs([
            "质量门禁", "单条评审", "模板与追踪", "标准目录", "知识来源",
        ])

        with tab_gate:
            summary = quality_summary(requirements)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("需求数量", summary["count"])
            c2.metric("平均质量分", f"{summary['average']:.1f}")
            c3.metric("可提交评审", summary["review_ready"])
            c4.metric("低于门禁", summary["below_gate"])

            if not requirements:
                st.info("当前车型暂无需求。先在“需求规范”中创建需求，再进行批量质量检查。")
            else:
                outgoing = {}
                incoming = {}
                for link in links:
                    if link.source_type == "Requirement":
                        outgoing.setdefault(link.source_id, []).append(link)
                    if link.target_type == "Requirement":
                        incoming.setdefault(link.target_id, []).append(link)

                rows = []
                for req in requirements:
                    result = assess_requirement_quality(
                        req.text,
                        source=req.source or "",
                        rationale=req.rationale or "",
                        verification_method=req.verification_method or "",
                        acceptance_criteria=req.acceptance_criteria or "",
                        req_type=req.req_type,
                        asil_level=req.asil_level or "",
                    )
                    issue_codes = ", ".join(item["code"] for item in result["findings"] if item["severity"] != "信息")
                    rows.append({
                        "需求": f"{req.req_id} · {req.title}",
                        "类型": req.req_type,
                        "状态": req.status,
                        "得分": result["score"],
                        "门禁": "可提交" if result["ready_for_review"] else "需完善",
                        "上游": len(incoming.get(req.id, [])),
                        "下游": len(outgoing.get(req.id, [])),
                        "主要问题": issue_codes or "—",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                st.caption("质量分是可解释的规则检查结果，不评价需求的领域技术正确性。门禁阈值为 75 分且无阻断问题。")

        with tab_review:
            mode = st.radio("评审对象", ["已有需求", "临时文本"], horizontal=True)
            if mode == "已有需求":
                if not requirements:
                    st.info("暂无已有需求可供评审。")
                else:
                    selected = st.selectbox(
                        "选择需求", requirements,
                        format_func=lambda req: f"{req.req_id} · {req.title}",
                    )
                    result = assess_requirement_quality(
                        selected.text,
                        source=selected.source or "",
                        rationale=selected.rationale or "",
                        verification_method=selected.verification_method or "",
                        acceptance_criteria=selected.acceptance_criteria or "",
                        req_type=selected.req_type,
                        asil_level=selected.asil_level or "",
                    )
                    st.code(selected.text, language=None)
                    _render_findings(result)
            else:
                req_type = st.selectbox("需求类型", list(REQUIREMENT_TEMPLATES))
                text = st.text_area("需求正文", height=130)
                c1, c2 = st.columns(2)
                source = c1.text_input("上游来源")
                verification = c2.selectbox("验证方法", ["", "Test", "Analysis", "Inspection", "Demonstration"])
                acceptance = st.text_area("验收准则", height=90)
                c3, c4 = st.columns(2)
                rationale = c3.text_input("理由/假设")
                asil = c4.selectbox("ASIL", ["", "QM", "ASIL-A", "ASIL-B", "ASIL-C", "ASIL-D"])
                if st.button("运行质量评审", type="primary"):
                    _render_findings(assess_requirement_quality(
                        text,
                        source=source,
                        rationale=rationale,
                        verification_method=verification,
                        acceptance_criteria=acceptance,
                        req_type=req_type,
                        asil_level=asil,
                    ))

        with tab_templates:
            st.markdown("#### 需求写作模板")
            for key, template in REQUIREMENT_TEMPLATES.items():
                with st.expander(f"{template['name']} · {key}", expanded=key == "Functional"):
                    st.markdown(f"**正文模板**：{template['text']}")
                    st.markdown(f"**验收模板**：{template['acceptance']}")
                    st.caption(f"最小信息集：{template['minimum']}")

            st.markdown("#### 追踪蓝图")
            for blueprint in TRACEABILITY_BLUEPRINTS:
                st.markdown(f"**{blueprint['name']}**")
                st.code(" → ".join(blueprint["nodes"]), language=None)
                st.caption(f"门禁：{blueprint['gate']}")

        with tab_standards:
            st.markdown("#### 经版本校正的参考目录")
            st.dataframe(pd.DataFrame([{
                "标准/模型": item["code"],
                "名称": item["name"],
                "状态": item["status"],
                "在本工具中的用途": item["use"],
                "边界": item["boundary"],
                "官方入口": item["url"],
            } for item in STANDARDS_CATALOG]), use_container_width=True, hide_index=True)
            st.caption("IEEE 830 和 Automotive SPICE 3.1 等旧引用没有作为当前默认基线。")

        with tab_source:
            st.markdown("#### 本地参考快照")
            st.code(LOCAL_REFERENCE_PATH, language=None)
            st.markdown(f"- 上游仓库：[{UPSTREAM_REPOSITORY}]({UPSTREAM_REPOSITORY})")
            st.markdown(f"- 固定提交：`{UPSTREAM_COMMIT}`")
            st.markdown("- 提炼原则：需求工程优先、官方版本校正、保留适用边界、不复制受版权保护的标准正文。")
            st.markdown("- 重点来源：requirements analyst、ASPICE SWE.1、software safety requirements、中国标准与 SOTIF 目录。")
    finally:
        db.close()
