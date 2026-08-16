"""Signal data-flow normalization, editing, and Streamlit component adapter."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import streamlit.components.v1 as components

from db import ArtifactChangeRecord, Signal, SignalEndpoint

_FIELD_PATTERNS = {
    "bus": re.compile(r"^\s*总线\s*[:：]\s*(.*?)\s*$", re.MULTILINE),
    "tx": re.compile(r"^\s*发送节点\s*[:：]\s*(.*?)\s*$", re.MULTILINE),
    "rx": re.compile(r"^\s*接收节点\s*[:：]\s*(.*?)\s*$", re.MULTILINE),
    "source": re.compile(r"^\s*来源\s*[:：]\s*(.*?)\s*$", re.MULTILINE),
}
_EMPTY_ENDPOINTS = {"", "?", "-", "none", "null", "vector__xxx", "vector_xxx"}


@dataclass(frozen=True)
class SignalMetadata:
    bus: str
    tx: str
    receivers: tuple[str, ...]
    source: str


def _field(description: str | None, name: str) -> str:
    match = _FIELD_PATTERNS[name].search(description or "")
    return match.group(1).strip() if match else ""


def _clean_endpoint(value: str | None) -> str:
    endpoint = (value or "").strip()
    return "" if endpoint.lower() in _EMPTY_ENDPOINTS else endpoint


def parse_signal_metadata(signal: Signal) -> SignalMetadata:
    """Extract DBC provenance without changing the source text."""
    rx_text = _field(signal.description, "rx")
    receivers: list[str] = []
    for item in re.split(r"[,，;；|/]", rx_text):
        endpoint = _clean_endpoint(item)
        if endpoint and endpoint not in receivers:
            receivers.append(endpoint)
    return SignalMetadata(
        bus=_field(signal.description, "bus") or "未标注总线",
        tx=_clean_endpoint(_field(signal.description, "tx")) or _clean_endpoint(signal.module),
        receivers=tuple(receivers),
        source=_field(signal.description, "source"),
    )


def sync_signal_endpoints(session, project_id: int) -> dict[str, int]:
    """Idempotently materialize DBC Tx/Rx endpoints for one project."""
    signals = session.query(Signal).filter_by(project_id=project_id).all()
    existing = session.query(SignalEndpoint).filter_by(project_id=project_id).all()
    endpoint_keys = {
        (row.signal_id, row.endpoint_role, row.dbc_ecu_name)
        for row in existing
        if row.dbc_ecu_name
    }
    added_tx = 0
    added_rx = 0
    for signal in signals:
        meta = parse_signal_metadata(signal)
        if meta.tx and (signal.id, "Tx", meta.tx) not in endpoint_keys:
            session.add(SignalEndpoint(
                project_id=project_id,
                signal_id=signal.id,
                endpoint_role="Tx",
                dbc_ecu_name=meta.tx,
                ecu_name=meta.tx,
                source_kind="DBC",
            ))
            endpoint_keys.add((signal.id, "Tx", meta.tx))
            added_tx += 1
        for receiver in meta.receivers:
            key = (signal.id, "Rx", receiver)
            if key in endpoint_keys:
                continue
            session.add(SignalEndpoint(
                project_id=project_id,
                signal_id=signal.id,
                endpoint_role="Rx",
                dbc_ecu_name=receiver,
                ecu_name=receiver,
                source_kind="DBC",
            ))
            endpoint_keys.add(key)
            added_rx += 1
    if added_tx or added_rx:
        session.commit()
    return {"signals": len(signals), "tx_added": added_tx, "rx_added": added_rx}


def move_receiver(
    session,
    *,
    project_id: int,
    endpoint_id: int,
    new_ecu: str,
    reason: str,
    changed_by: str = "当前用户",
) -> SignalEndpoint:
    """Move one effective Rx endpoint and preserve its original DBC endpoint."""
    endpoint = session.query(SignalEndpoint).filter_by(
        id=endpoint_id,
        project_id=project_id,
        endpoint_role="Rx",
        is_active=True,
    ).first()
    if endpoint is None:
        raise ValueError("接收端点不存在或不属于当前车型")
    new_ecu = _clean_endpoint(new_ecu)
    if not new_ecu:
        raise ValueError("新的接收 ECU 不能为空")
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("请填写本次端点变更原因")
    old_ecu = endpoint.ecu_name
    if old_ecu == new_ecu:
        raise ValueError("新的接收 ECU 与当前端点相同")
    duplicate = session.query(SignalEndpoint).filter_by(
        project_id=project_id,
        signal_id=endpoint.signal_id,
        endpoint_role="Rx",
        ecu_name=new_ecu,
        is_active=True,
    ).first()
    if duplicate and duplicate.id != endpoint.id:
        raise ValueError(f"该信号已经分配给接收 ECU {new_ecu}")

    endpoint.ecu_name = new_ecu
    endpoint.source_kind = "Manual"
    endpoint.updated_at = datetime.utcnow()
    session.add(ArtifactChangeRecord(
        project_id=project_id,
        artifact_type="SignalEndpoint",
        artifact_id=endpoint.id,
        change_type="Reassign",
        field_name="ecu_name",
        old_value=old_ecu,
        new_value=new_ecu,
        reason=reason,
        changed_by=changed_by,
    ))
    session.commit()
    return endpoint


def _validated_reason(reason: str) -> str:
    value = (reason or "").strip()
    if not value:
        raise ValueError("请填写本次端点变更原因")
    return value


def _signal_in_project(session, project_id: int, signal_id: int) -> Signal:
    signal = session.query(Signal).filter_by(id=signal_id, project_id=project_id).first()
    if signal is None:
        raise ValueError("信号不存在或不属于当前车型")
    return signal


def _receiver_endpoint(session, project_id: int, endpoint_id: int, *, active: bool) -> SignalEndpoint:
    endpoint = session.query(SignalEndpoint).filter_by(
        id=endpoint_id,
        project_id=project_id,
        endpoint_role="Rx",
        is_active=active,
    ).first()
    if endpoint is None:
        state = "有效" if active else "已删除"
        raise ValueError(f"{state}接收端点不存在或不属于当前车型")
    return endpoint


def _record_endpoint_change(
    session,
    *,
    project_id: int,
    endpoint: SignalEndpoint,
    change_type: str,
    field_name: str,
    old_value: str | None,
    new_value: str | None,
    reason: str,
    changed_by: str,
) -> None:
    session.add(ArtifactChangeRecord(
        project_id=project_id,
        artifact_type="SignalEndpoint",
        artifact_id=endpoint.id,
        change_type=change_type,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        changed_by=changed_by,
    ))


def add_receiver(
    session,
    *,
    project_id: int,
    signal_id: int,
    new_ecu: str,
    reason: str,
    changed_by: str = "当前用户",
) -> SignalEndpoint:
    """Add an additional Rx branch without replacing existing receivers."""
    _signal_in_project(session, project_id, signal_id)
    new_ecu = _clean_endpoint(new_ecu)
    if not new_ecu:
        raise ValueError("新的接收 ECU 不能为空")
    reason = _validated_reason(reason)
    duplicate = session.query(SignalEndpoint).filter_by(
        project_id=project_id,
        signal_id=signal_id,
        endpoint_role="Rx",
        ecu_name=new_ecu,
        is_active=True,
    ).first()
    if duplicate:
        raise ValueError(f"该信号已经连接到接收 ECU {new_ecu}")

    inactive = session.query(SignalEndpoint).filter_by(
        project_id=project_id,
        signal_id=signal_id,
        endpoint_role="Rx",
        ecu_name=new_ecu,
        is_active=False,
    ).first()
    if inactive:
        inactive.is_active = True
        inactive.updated_at = datetime.utcnow()
        endpoint = inactive
        change_type = "Reactivate"
    else:
        endpoint = SignalEndpoint(
            project_id=project_id,
            signal_id=signal_id,
            endpoint_role="Rx",
            dbc_ecu_name=None,
            ecu_name=new_ecu,
            source_kind="Manual",
            is_active=True,
        )
        session.add(endpoint)
        session.flush()
        change_type = "Add"
    _record_endpoint_change(
        session,
        project_id=project_id,
        endpoint=endpoint,
        change_type=change_type,
        field_name="is_active",
        old_value="false" if change_type == "Reactivate" else None,
        new_value=new_ecu,
        reason=reason,
        changed_by=changed_by,
    )
    session.commit()
    return endpoint


def remove_receiver(
    session,
    *,
    project_id: int,
    endpoint_id: int,
    reason: str,
    changed_by: str = "当前用户",
) -> SignalEndpoint:
    """Deactivate an Rx branch while retaining its DBC/manual provenance."""
    endpoint = _receiver_endpoint(session, project_id, endpoint_id, active=True)
    reason = _validated_reason(reason)
    endpoint.is_active = False
    endpoint.updated_at = datetime.utcnow()
    _record_endpoint_change(
        session,
        project_id=project_id,
        endpoint=endpoint,
        change_type="Remove",
        field_name="is_active",
        old_value=endpoint.ecu_name,
        new_value="false",
        reason=reason,
        changed_by=changed_by,
    )
    session.commit()
    return endpoint


def reactivate_receiver(
    session,
    *,
    project_id: int,
    endpoint_id: int,
    reason: str,
    changed_by: str = "当前用户",
) -> SignalEndpoint:
    """Restore a previously removed Rx branch as the current project endpoint."""
    endpoint = _receiver_endpoint(session, project_id, endpoint_id, active=False)
    reason = _validated_reason(reason)
    duplicate = session.query(SignalEndpoint).filter_by(
        project_id=project_id,
        signal_id=endpoint.signal_id,
        endpoint_role="Rx",
        ecu_name=endpoint.ecu_name,
        is_active=True,
    ).first()
    if duplicate:
        raise ValueError(f"该信号已经连接到接收 ECU {endpoint.ecu_name}")
    endpoint.is_active = True
    endpoint.updated_at = datetime.utcnow()
    _record_endpoint_change(
        session,
        project_id=project_id,
        endpoint=endpoint,
        change_type="Reactivate",
        field_name="is_active",
        old_value="false",
        new_value=endpoint.ecu_name,
        reason=reason,
        changed_by=changed_by,
    )
    session.commit()
    return endpoint


def reset_receiver_to_dbc(
    session,
    *,
    project_id: int,
    endpoint_id: int,
    reason: str,
    changed_by: str = "当前用户",
) -> SignalEndpoint:
    endpoint = session.query(SignalEndpoint).filter_by(
        id=endpoint_id,
        project_id=project_id,
        endpoint_role="Rx",
        is_active=True,
    ).first()
    if endpoint is None or not endpoint.dbc_ecu_name:
        raise ValueError("该端点没有可恢复的 DBC 原始节点")
    if endpoint.ecu_name == endpoint.dbc_ecu_name:
        raise ValueError("当前端点已经与 DBC 原始节点一致")
    return move_receiver(
        session,
        project_id=project_id,
        endpoint_id=endpoint_id,
        new_ecu=endpoint.dbc_ecu_name,
        reason=reason,
        changed_by=changed_by,
    )


def effective_ecus(endpoints: Iterable[SignalEndpoint]) -> list[str]:
    return sorted({row.ecu_name for row in endpoints if row.is_active and row.ecu_name})


_COMPONENT_DIR = Path(__file__).with_name("signal_flow_component")
_signal_flow_editor = components.declare_component(
    "ee_req_signal_flow_editor",
    path=str(_COMPONENT_DIR),
)


def signal_flow_editor(
    *,
    mode: str,
    message: dict,
    signals: list[dict],
    ecu_candidates: list[str],
    selected_signal_id: int | None,
    viewport_state: dict | None,
    view_state_key: str,
    line_style: str,
    compact: bool,
    key: str,
):
    """Render the editable graph. Events are returned as JSON dictionaries."""
    return _signal_flow_editor(
        mode=mode,
        message=message,
        signals=signals,
        ecuCandidates=ecu_candidates,
        selectedSignalId=selected_signal_id,
        viewportState=viewport_state or {},
        viewStateKey=view_state_key,
        lineStyle=line_style,
        compact=compact,
        eventSeed=uuid.uuid4().hex,
        key=key,
        default=None,
    )
