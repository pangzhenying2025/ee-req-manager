"""Requirement dimensions and audit text; no UI or database dependencies."""

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


def legacy_requirement_type(req_level: str, req_nature: str) -> str:
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


def automatic_change_reason(changes: list[tuple[str, object, object]]) -> str:
    """Build an auditable reason when the editor leaves the note empty."""
    summaries = []
    for name, old, new in changes:
        old_text = "—" if old in (None, "") else str(old)
        new_text = "—" if new in (None, "") else str(new)
        summaries.append(f"{CHANGE_FIELD_LABELS.get(name, name)}：{old_text} → {new_text}")
    return "系统自动记录：" + "；".join(summaries)
