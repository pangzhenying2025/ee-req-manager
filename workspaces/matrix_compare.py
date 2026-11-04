"""Read-only communication matrix comparison workspace."""

import os
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from communication_matrix import SUPPORTED_MATRIX_TYPES, compare_matrices, load_matrix


def _load_uploaded_matrix(uploaded_file):
    suffix = Path(uploaded_file.name).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name
    try:
        return load_matrix(tmp_path)
    finally:
        os.unlink(tmp_path)


def page_matrix_compare():
    st.title("🧮 通信矩阵版本对比")
    st.caption("用 canmatrix 统一读取两个版本，逐项识别信号新增、删除及工程属性变化。仅分析上传文件，不修改车型数据库。")

    base_col, candidate_col = st.columns(2, gap="large")
    supported = list(SUPPORTED_MATRIX_TYPES)
    with base_col:
        baseline_file = st.file_uploader(
            "基线版本",
            type=supported,
            key="matrix_compare_baseline",
            help="例如供应商上一次发布的 DBC/XLSX。",
        )
    with candidate_col:
        candidate_file = st.file_uploader(
            "候选版本",
            type=supported,
            key="matrix_compare_candidate",
            help="例如本次待评审或待发布的 DBC/XLSX。",
        )

    if not baseline_file or not candidate_file:
        st.info("请分别上传基线版本和候选版本。支持 DBC、XLSX、DBF、SYM、JSON。")
        return

    try:
        baseline = _load_uploaded_matrix(baseline_file)
        candidate = _load_uploaded_matrix(candidate_file)
        summary, differences = compare_matrices(baseline, candidate)
    except Exception as exc:
        st.error(f"通信矩阵解析失败：{exc}")
        st.caption("如果是企业自定义 Excel 模板，请继续使用“Excel通讯矩阵”导入页；该对比页读取 canmatrix 标准格式。")
        return

    metric_names = ["基线信号", "候选信号", "新增信号", "删除信号", "修改信号", "差异项"]
    metric_cols = st.columns(len(metric_names))
    for column, name in zip(metric_cols, metric_names):
        column.metric(name, summary[name])

    st.subheader("差异明细")
    if not differences:
        st.success("两个通信矩阵的信号及工程属性一致。")
        return

    diff_frame = pd.DataFrame(differences)
    change_filter = st.multiselect(
        "变更类型",
        ["新增", "删除", "修改"],
        default=["新增", "删除", "修改"],
        key="matrix_compare_change_filter",
    )
    search_text = st.text_input("搜索 CAN ID / 报文 / 信号 / 属性", key="matrix_compare_search").strip()
    display_frame = diff_frame[diff_frame["变更"].isin(change_filter)]
    if search_text:
        mask = display_frame.astype(str).apply(
            lambda column: column.str.contains(search_text, case=False, regex=False)
        ).any(axis=1)
        display_frame = display_frame[mask]
    st.dataframe(display_frame, use_container_width=True, hide_index=True)
    st.download_button(
        "📥 导出差异 CSV",
        diff_frame.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"通信矩阵差异_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
