"""Streamlit adapter; endpoint operations live in services.signal_endpoints."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import streamlit.components.v1 as components

from services.signal_endpoints import (
    SignalMetadata as SignalMetadata,
)
from services.signal_endpoints import (
    add_receiver as add_receiver,
)
from services.signal_endpoints import (
    effective_ecus as effective_ecus,
)
from services.signal_endpoints import (
    move_receiver as move_receiver,
)
from services.signal_endpoints import (
    parse_signal_metadata as parse_signal_metadata,
)
from services.signal_endpoints import (
    reactivate_receiver as reactivate_receiver,
)
from services.signal_endpoints import (
    remove_receiver as remove_receiver,
)
from services.signal_endpoints import (
    reset_receiver_to_dbc as reset_receiver_to_dbc,
)
from services.signal_endpoints import (
    sync_signal_endpoints as sync_signal_endpoints,
)

_COMPONENT_ROOT = Path(__file__).with_name("signal_flow_component")
_COMPONENT_DIR = _COMPONENT_ROOT / "dist"
_DEV_URL = os.environ.get("EE_REQ_COMPONENT_DEV_URL", "").strip()
if not _DEV_URL and not (_COMPONENT_DIR / "index.html").exists():
    raise RuntimeError("画布资源未构建。请运行 python scripts/dev.py build，或用开发模式启动。")
_signal_flow_editor = components.declare_component(
    "ee_req_signal_flow_editor",
    **({"url": _DEV_URL} if _DEV_URL else {"path": str(_COMPONENT_DIR)}),
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
