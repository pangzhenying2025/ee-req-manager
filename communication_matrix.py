"""CAN communication-matrix loading and semantic comparison.

The adapter deliberately keeps canmatrix objects outside the UI layer.  This
makes the comparison deterministic, testable, and reusable by a future import
pipeline without coupling project data to uploaded files.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import canmatrix.formats

SUPPORTED_MATRIX_TYPES = ("dbc", "xlsx", "dbf", "sym", "json")


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@dataclass(frozen=True)
class MatrixSignal:
    frame_id: int
    frame_name: str
    frame_size: int
    transmitters: tuple[str, ...]
    name: str
    start_bit: int
    bit_length: int
    byte_order: str
    value_type: str
    factor: Any
    offset: Any
    minimum: Any
    maximum: Any
    unit: str
    receivers: tuple[str, ...]
    cycle_time: int

    @property
    def key(self) -> tuple[int, str]:
        return self.frame_id, self.name


def load_matrix(path: str | Path) -> list[MatrixSignal]:
    """Load all clusters from a canmatrix-supported file into a stable model."""
    file_path = Path(path)
    import_type = file_path.suffix.lower().lstrip(".")
    if import_type not in SUPPORTED_MATRIX_TYPES:
        raise ValueError(f"不支持的通信矩阵格式：.{import_type}")

    databases = canmatrix.formats.loadp(str(file_path), import_type=import_type)
    normalized: list[MatrixSignal] = []
    for matrix in databases.values():
        for frame in matrix.frames:
            frame_id = int(frame.arbitration_id.id)
            transmitters = tuple(sorted(str(item) for item in frame.transmitters))
            for signal in frame.signals:
                normalized.append(MatrixSignal(
                    frame_id=frame_id,
                    frame_name=str(frame.name),
                    frame_size=int(frame.size),
                    transmitters=transmitters,
                    name=str(signal.name),
                    start_bit=int(signal.get_startbit()),
                    bit_length=int(signal.size),
                    byte_order="Intel" if signal.is_little_endian else "Motorola",
                    value_type="Signed" if signal.is_signed else "Unsigned",
                    factor=_plain(signal.factor),
                    offset=_plain(signal.offset),
                    minimum=_plain(signal.min),
                    maximum=_plain(signal.max),
                    unit=str(signal.unit or ""),
                    receivers=tuple(sorted(str(item) for item in signal.receivers)),
                    cycle_time=int(signal.cycle_time or getattr(frame, "cycle_time", 0) or 0),
                ))
    return sorted(normalized, key=lambda item: (item.frame_id, item.start_bit, item.name))


_FIELD_LABELS = {
    "frame_name": "报文名称",
    "frame_size": "DLC",
    "transmitters": "发送节点",
    "start_bit": "起始位",
    "bit_length": "位长",
    "byte_order": "字节序",
    "value_type": "值类型",
    "factor": "精度 Factor",
    "offset": "偏移量 Offset",
    "minimum": "最小值",
    "maximum": "最大值",
    "unit": "单位",
    "receivers": "接收节点",
    "cycle_time": "周期(ms)",
}


def _display(value: Any) -> str:
    if isinstance(value, tuple):
        return ", ".join(value) or "—"
    if value in (None, ""):
        return "—"
    return str(value)


def compare_matrices(
    baseline: Iterable[MatrixSignal],
    candidate: Iterable[MatrixSignal],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Return summary counts and field-level differences for two matrices."""
    old = {item.key: item for item in baseline}
    new = {item.key: item for item in candidate}
    rows: list[dict[str, Any]] = []
    changed_signals: set[tuple[int, str]] = set()
    added = set(new) - set(old)
    removed = set(old) - set(new)

    for key in sorted(added):
        item = new[key]
        rows.append({
            "变更": "新增",
            "CAN ID": f"0x{item.frame_id:X}",
            "报文": item.frame_name,
            "信号": item.name,
            "属性": "完整信号",
            "基线值": "—",
            "候选值": "新增",
        })
    for key in sorted(removed):
        item = old[key]
        rows.append({
            "变更": "删除",
            "CAN ID": f"0x{item.frame_id:X}",
            "报文": item.frame_name,
            "信号": item.name,
            "属性": "完整信号",
            "基线值": "存在",
            "候选值": "—",
        })
    for key in sorted(set(old) & set(new)):
        before = asdict(old[key])
        after = asdict(new[key])
        for field, label in _FIELD_LABELS.items():
            if before[field] == after[field]:
                continue
            changed_signals.add(key)
            rows.append({
                "变更": "修改",
                "CAN ID": f"0x{key[0]:X}",
                "报文": after["frame_name"],
                "信号": key[1],
                "属性": label,
                "基线值": _display(before[field]),
                "候选值": _display(after[field]),
            })

    summary = {
        "基线信号": len(old),
        "候选信号": len(new),
        "新增信号": len(added),
        "删除信号": len(removed),
        "修改信号": len(changed_signals),
        "未变化信号": len((set(old) & set(new)) - changed_signals),
        "差异项": len(rows),
    }
    return summary, rows
