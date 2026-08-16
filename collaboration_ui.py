"""Streamlit UI helpers for LAN presence and artifact edit ownership."""

from __future__ import annotations

import uuid

import streamlit as st

from collaboration import (
    acquire_lock,
    active_sessions,
    current_lock,
    owns_lock,
    release_lock,
    touch_session,
)
from db import SessionLocal


def initialize_identity() -> tuple[str, str]:
    if "collab_session_id" not in st.session_state:
        st.session_state.collab_session_id = uuid.uuid4().hex
    if "collab_user_name" not in st.session_state:
        suffix = st.session_state.collab_session_id[-4:].upper()
        st.session_state.collab_user_name = f"工程师-{suffix}"
    user_name = st.sidebar.text_input(
        "协作者名称",
        key="collab_user_name",
        help="该名称会显示给同一车型的在线成员，并写入需求和架构变更记录。",
    ).strip()
    if not user_name:
        user_name = f"工程师-{st.session_state.collab_session_id[-4:].upper()}"
    return st.session_state.collab_session_id, user_name


def collaborator_name() -> str:
    return st.session_state.get("collab_user_name", "当前用户").strip() or "当前用户"


def collaborator_session_id() -> str:
    return st.session_state.get("collab_session_id", "")


@st.fragment(run_every="10s")
def render_presence(project_id: int, page_name: str) -> None:
    session_id = collaborator_session_id()
    user_name = collaborator_name()
    if not session_id:
        return
    try:
        ip_address = str(st.context.ip_address or "")
    except (AttributeError, RuntimeError):
        ip_address = ""
    db = SessionLocal()
    try:
        touch_session(
            db,
            session_id=session_id,
            user_name=user_name,
            project_id=project_id,
            page_name=page_name,
            ip_address=ip_address,
        )
        rows = active_sessions(db, project_id)
        with st.sidebar.expander(f"🟢 在线协作 · {len(rows)}", expanded=False):
            for row in rows:
                self_mark = "（我）" if row.session_id == session_id else ""
                location = row.page_name or "浏览中"
                st.caption(f"{row.user_name}{self_mark} · {location}")
    finally:
        db.close()


def render_edit_lock(
    *,
    project_id: int,
    artifact_type: str,
    artifact_id: int,
    artifact_label: str,
) -> bool:
    """Render edit ownership controls and return whether this session may edit."""
    session_id = collaborator_session_id()
    user_name = collaborator_name()
    if not session_id:
        st.error("当前协作会话无效，请刷新页面后重试。")
        return False
    db = SessionLocal()
    try:
        row = current_lock(
            db,
            project_id=project_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
        )
        key = f"lock_{project_id}_{artifact_type}_{artifact_id}"
        if row is not None and row.session_id == session_id:
            owns_lock(
                db,
                project_id=project_id,
                artifact_type=artifact_type,
                artifact_id=artifact_id,
                session_id=session_id,
                refresh=True,
            )
            c1, c2 = st.columns([4, 1])
            c1.success(f"你正在编辑：{artifact_label}（编辑权保留 5 分钟）")
            if c2.button("释放", key=f"release_{key}", use_container_width=True):
                release_lock(
                    db,
                    project_id=project_id,
                    artifact_type=artifact_type,
                    artifact_id=artifact_id,
                    session_id=session_id,
                )
                st.rerun()
            return True
        if row is not None:
            st.warning(
                f"{artifact_label} 正由「{row.user_name}」编辑。"
                "你目前只能查看，编辑权超时后会自动释放。"
            )
            return False
        if st.button("开始编辑", type="primary", key=f"acquire_{key}"):
            result = acquire_lock(
                db,
                project_id=project_id,
                artifact_type=artifact_type,
                artifact_id=artifact_id,
                session_id=session_id,
                user_name=user_name,
            )
            if result.acquired:
                st.rerun()
            else:
                st.warning(f"编辑权刚刚被「{result.owner_name}」取得，请稍后再试。")
        else:
            st.info("点击“开始编辑”取得编辑权；其他在线成员仍可查看，但不能同时覆盖该对象。")
        return False
    finally:
        db.close()


def verify_edit_lock(project_id: int, artifact_type: str, artifact_id: int) -> bool:
    db = SessionLocal()
    try:
        return owns_lock(
            db,
            project_id=project_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            session_id=collaborator_session_id(),
            refresh=True,
        )
    finally:
        db.close()


def release_current_lock(project_id: int, artifact_type: str, artifact_id: int) -> None:
    db = SessionLocal()
    try:
        release_lock(
            db,
            project_id=project_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            session_id=collaborator_session_id(),
        )
    finally:
        db.close()
