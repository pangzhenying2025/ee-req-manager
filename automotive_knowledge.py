"""Curated automotive requirements-engineering knowledge and deterministic checks.

The upstream automotive agents repository is a useful idea library, not a
normative standards source.  This module keeps only reviewed, product-relevant
patterns and records where each pattern came from.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass


UPSTREAM_REPOSITORY = "https://github.com/sydyg/automotive-claude-code-agents"
UPSTREAM_COMMIT = "e2de91aec69c6221c72088f14abd06c69b01c12b"
LOCAL_REFERENCE_PATH = r"E:\hermes\.codex-review\automotive-claude-code-agents"


@dataclass(frozen=True)
class QualityFinding:
    code: str
    severity: str
    message: str
    suggestion: str
    deduction: int


STANDARDS_CATALOG = [
    {
        "code": "ISO/IEC/IEEE 29148:2018",
        "name": "需求工程生命周期过程",
        "status": "Active（IEEE 页面）",
        "use": "需求属性、质量特征、需求工程过程与信息项",
        "url": "https://standards.ieee.org/ieee/802.1Q/6937/",
        "boundary": "项目仅保存方法摘要；实施时应使用组织持有的正式标准文本。",
    },
    {
        "code": "Automotive SPICE 4.0",
        "name": "汽车软件过程参考模型",
        "status": "Current reference model",
        "use": "SYS/SWE 过程、工作产品、双向追踪和评审证据",
        "url": "https://automotivespice.com/fileadmin/software-download/automotiveSIG_PRM_v45.pdf",
        "boundary": "本工具辅助准备证据，不代表通过 Automotive SPICE 评估。",
    },
    {
        "code": "ISO 26262:2018",
        "name": "道路车辆功能安全",
        "status": "Published",
        "use": "安全生命周期、HARA、安全目标及 FSR/TSR/HSR/SWR 追踪",
        "url": "https://www.iso.org/publication/PUB200262.html",
        "boundary": "模板不能替代安全经理、独立确认措施或正式安全评审。",
    },
    {
        "code": "ISO 21448:2022",
        "name": "预期功能安全（SOTIF）",
        "status": "Published；新版处于修订开发阶段",
        "use": "功能不足、触发条件、合理可预见误用、场景驱动 V&V",
        "url": "https://www.iso.org/standard/77490.html",
        "boundary": "仅在感知、复杂算法和预期功能安全场景下按适用性采用。",
    },
]


TRACEABILITY_BLUEPRINTS = [
    {
        "name": "通用 E/E 需求闭环",
        "nodes": [
            "利益相关方需求", "整车需求", "功能/系统需求", "逻辑功能",
            "ECU 分配", "接口/信号", "验证需求/测试",
        ],
        "gate": "非顶层需求有来源，工程需求有架构分配，已批准需求有验证链路。",
    },
    {
        "name": "ISO 26262 安全需求链",
        "nodes": [
            "危险事件/HARA", "安全目标 SG", "功能安全需求 FSR",
            "技术安全需求 TSR", "硬件/软件安全需求 HSR/SWR", "安全机制", "验证证据",
        ],
        "gate": "ASIL、假设、分配、验证方法和确认状态沿链路保持一致并可审计。",
    },
    {
        "name": "Automotive SPICE V 模型证据链",
        "nodes": [
            "利益相关方需求", "系统需求 SYS.2", "系统架构 SYS.3",
            "软件需求 SWE.1", "软件架构 SWE.2", "实现 SWE.3", "验证 SWE.4-6",
        ],
        "gate": "需求、架构、实现和测试之间保持双向追踪，并保留评审与基线证据。",
    },
    {
        "name": "SOTIF 场景链",
        "nodes": [
            "预期功能/ODD", "功能不足", "触发条件", "危险场景",
            "风险降低措施", "场景测试", "残余风险论证",
        ],
        "gate": "区分故障型功能安全与无故障功能不足，覆盖已知/未知及合理可预见误用。",
    },
]


REQUIREMENT_TEMPLATES = {
    "Functional": {
        "name": "功能/系统需求",
        "text": "在【前置条件/运行模式】下，当【触发事件】发生时，【系统/ECU】应在【时间限值】内【执行可观察行为】，并满足【量化边界】。",
        "acceptance": "给定【初始状态】，当【输入/事件】发生，则【输出/状态】应满足【数值、单位、容差和时限】。",
        "minimum": "主体、条件、触发、行为、边界、验证方法",
    },
    "Interface": {
        "name": "接口需求",
        "text": "【发送方】应通过【总线/接口】以【周期/事件】发送【数据项】，其范围为【最小值～最大值】【单位】，分辨率为【值】，超时后【接收方】应【降级行为】。",
        "acceptance": "验证接口、数据类型、范围、单位、刷新率、超时与错误处理均符合接口控制文件。",
        "minimum": "提供方、使用方、数据语义、单位、时序、错误处理",
    },
    "Safety": {
        "name": "安全需求",
        "text": "当检测到【故障/异常条件】时，【系统/安全机制】应在【FTTI/时间限值】内进入【安全状态/降级状态】，并保持至【恢复条件】，ASIL 为【等级】。",
        "acceptance": "通过【故障注入/分析/测试】确认检测时间、反应时间、安全状态和诊断记录满足分配的安全需求。",
        "minimum": "来源安全目标、ASIL、故障条件、检测、反应、FTTI、安全状态、验证",
    },
    "Verification": {
        "name": "验证需求",
        "text": "验证活动应在【环境/配置】下施加【输入与边界条件】，确认【被验证需求】的【预期结果】，判定准则为【量化通过条件】。",
        "acceptance": "测试记录包含配置、输入、期望值、实测值、容差、结论及关联需求版本。",
        "minimum": "对象、环境、方法、输入、期望结果、判定准则、证据",
    },
}


_VAGUE_TERMS = {
    "尽快", "快速", "及时", "适当", "合理", "必要时", "正常", "稳定",
    "高效", "友好", "足够", "等", "等等", "as soon as possible", "quickly",
    "appropriately", "normally", "sufficient", "user-friendly",
}
_QUANTIFIED_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*(?:ms|s|秒|毫秒|分钟|%|V|A|mA|km/h|m/s|Hz|℃|°C|字节|bit|次)",
    re.IGNORECASE,
)


def _obligation_count(text: str) -> int:
    """Count obligations without treating Chinese words such as 响应 as 应."""
    chinese_text = text.replace("响应", "").replace("相应", "")
    english_count = len(re.findall(r"\b(?:shall|must)\b", text, re.IGNORECASE))
    return chinese_text.count("应") + english_count


def assess_requirement_quality(
    text: str,
    *,
    source: str = "",
    rationale: str = "",
    verification_method: str = "",
    acceptance_criteria: str = "",
    req_type: str = "Functional",
    asil_level: str = "",
) -> dict:
    """Return an explainable, deterministic requirement-quality assessment."""
    normalized = " ".join((text or "").strip().split())
    lowered = normalized.lower()
    findings: list[QualityFinding] = []

    def add(code: str, severity: str, message: str, suggestion: str, deduction: int):
        findings.append(QualityFinding(code, severity, message, suggestion, deduction))

    if not normalized:
        add("EMPTY", "阻断", "需求正文为空。", "填写一个包含主体和可观察行为的完整需求。", 50)
    elif _obligation_count(lowered) == 0:
        add("OBLIGATION", "主要", "没有识别到明确的约束词（应/shall/must）。", "使用一致的强制性措辞表达义务。", 12)

    vague = sorted(term for term in _VAGUE_TERMS if term in lowered)
    if vague:
        add("VAGUE", "主要", f"包含模糊词：{'、'.join(vague)}。", "改成可测量的阈值、时限、状态或判定条件。", min(18, 6 + len(vague) * 3))

    obligation_count = _obligation_count(lowered)
    if obligation_count > 1 or normalized.count("；") > 1:
        add("ATOMIC", "建议", "一句中可能包含多个义务。", "拆分为可独立分配、变更和验证的原子需求。", 8)

    if len(normalized) < 12:
        add("SHORT", "主要", "需求正文过短，可能缺少条件或行为边界。", "补充运行条件、触发事件、响应和约束。", 10)
    if not source.strip():
        add("SOURCE", "主要", "缺少上游来源。", "关联客户、法规、安全目标或上级需求。", 10)
    if not verification_method.strip():
        add("VERIFY", "主要", "未指定验证方法。", "选择 Test、Analysis、Inspection 或 Demonstration。", 10)
    if not acceptance_criteria.strip():
        add("ACCEPTANCE", "主要", "缺少可执行的验收准则。", "使用 Given/When/Then 或量化输入—输出判定。", 12)

    combined = f"{normalized} {acceptance_criteria}"
    if req_type in {"Interface", "Safety", "Verification"} and not _QUANTIFIED_PATTERN.search(combined):
        add("MEASURABLE", "建议", "关键工程需求中未识别到数值、单位或时间边界。", "在适用时补充范围、单位、容差、周期、超时或 FTTI。", 8)

    if req_type == "Safety":
        if not asil_level or asil_level in {"-", "QM"}:
            add("ASIL", "主要", "安全需求未分配 ASIL。", "从安全目标或上游安全需求继承并确认 ASIL。", 12)
        safety_terms = ("安全状态", "降级", "safe state", "degraded", "故障", "fault")
        if not any(term in lowered for term in safety_terms):
            add("SAFE_STATE", "建议", "安全需求未明确故障条件或安全/降级反应。", "描述检测条件、反应、时间限制和恢复条件。", 8)

    if not rationale.strip():
        add("RATIONALE", "信息", "未填写设计理由。", "对派生需求或关键边界记录理由和假设。", 3)

    score = max(0, 100 - sum(item.deduction for item in findings))
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D"
    return {
        "score": score,
        "grade": grade,
        "ready_for_review": score >= 75 and not any(item.severity == "阻断" for item in findings),
        "findings": [asdict(item) for item in findings],
    }


def quality_summary(requirements) -> dict:
    """Aggregate assessments for ORM objects or object-like records."""
    results = []
    for req in requirements:
        results.append(assess_requirement_quality(
            getattr(req, "text", ""),
            source=getattr(req, "source", "") or "",
            rationale=getattr(req, "rationale", "") or "",
            verification_method=getattr(req, "verification_method", "") or "",
            acceptance_criteria=getattr(req, "acceptance_criteria", "") or "",
            req_type=getattr(req, "req_type", "Functional") or "Functional",
            asil_level=getattr(req, "asil_level", "") or "",
        ))
    return {
        "count": len(results),
        "average": round(sum(item["score"] for item in results) / len(results), 1) if results else 0.0,
        "review_ready": sum(item["ready_for_review"] for item in results),
        "below_gate": sum(not item["ready_for_review"] for item in results),
    }
