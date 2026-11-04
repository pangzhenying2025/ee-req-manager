"""Pure function/requirement trace-tree calculation."""

def build_function_requirement_trace(functions, relations, requirements, signals, links):
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
