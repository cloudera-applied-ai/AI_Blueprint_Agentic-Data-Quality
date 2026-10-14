"""Generate complete NiFi v2 flow definition JSON for data quality remediation."""

import json

from data.profiler import QualityIssue
from nifi.templates import (
    _uuid,
    _position,
    csv_reader_service,
    csv_writer_service,
    get_file_processor,
    route_on_attribute_processor,
    update_attribute_processor,
    put_file_processor,
    connection,
)


def _nifi_el_for_issue(issue: QualityIssue) -> str:
    """Generate NiFi Expression Language condition for an issue."""
    col = issue.field_name
    params = issue.params or {}

    if issue.issue_type == "invalid_phone_number":
        return f"${{{col}:matches('^[01].*')}}"
    elif issue.issue_type == "invalid_code_value":
        valid_values = params.get("valid_values")
        if valid_values:
            vals = ",".join(f"'{v.upper()}'" for v in valid_values)
            return f"${{{col}:toUpper():in({vals}):not()}}"
        return f"${{{col}:isEmpty():not()}}"
    elif issue.issue_type == "data_in_blank_field":
        return f"${{{col}:isEmpty():not()}}"
    elif issue.issue_type == "length_violation":
        max_len = params.get("max_length", 50)
        return f"${{{col}:length():gt({max_len})}}"
    elif issue.issue_type == "corrupted_data":
        return f"${{{col}:matches('[a-z]{{3,}}')}}"
    elif issue.issue_type == "format_mismatch":
        return f"${{{col}:matches('^[0-9]+$')}}"
    else:
        return f"${{{col}:isEmpty():not()}}"


def _fix_attributes_for_issue(issue: QualityIssue) -> dict[str, str]:
    """Generate UpdateAttribute properties to fix an issue."""
    col = issue.field_name

    if issue.issue_type in ("corrupted_data", "data_in_blank_field"):
        return {col: ""}
    elif issue.issue_type == "invalid_phone_number":
        return {f"{col}.quality_flag": "INVALID_PHONE", col: ""}
    elif issue.issue_type == "invalid_code_value":
        return {f"{col}.quality_flag": "INVALID_CODE"}
    elif issue.issue_type == "length_violation":
        return {f"{col}.quality_flag": "LENGTH_EXCEEDED"}
    elif issue.issue_type == "format_mismatch":
        return {f"{col}.quality_flag": "FORMAT_MISMATCH"}
    else:
        return {f"{col}.quality_flag": "QUALITY_ISSUE"}


def _assign_group_ids(components: list[dict], group_id: str) -> None:
    """Set groupIdentifier on all components and their nested source/destination."""
    for comp in components:
        comp["groupIdentifier"] = group_id
        # Connections have source/destination with groupId
        if "source" in comp and isinstance(comp["source"], dict):
            comp["source"]["groupId"] = group_id
        if "destination" in comp and isinstance(comp["destination"], dict):
            comp["destination"]["groupId"] = group_id


def generate_flow(
    issues: list[QualityIssue],
    flow_name: str = "AGT Data Quality Remediation",
) -> dict:
    """Build a NiFi 2.0 compatible flow definition JSON (importable via UI)."""
    processors = []
    connections = []
    controller_services = []

    # Controller services
    reader = csv_reader_service("|")
    writer = csv_writer_service("|")
    controller_services.extend([reader, writer])

    # Input processor
    input_proc = get_file_processor("/data/input")
    processors.append(input_proc)

    # Output processors
    valid_output = put_file_processor("PutFile - Valid Output", "/data/output/valid", 800, 0)
    corrected_output = put_file_processor("PutFile - Corrected Output", "/data/output/corrected", 800, 300)
    rejected_output = put_file_processor("PutFile - Rejected Output", "/data/output/rejected", 800, 600)
    processors.extend([valid_output, corrected_output, rejected_output])

    y_offset = 0
    prev_unmatched_source = input_proc["identifier"]
    prev_unmatched_rel = ["success"]

    for i, issue in enumerate(issues):
        y = y_offset + i * 200

        # Route processor for this issue
        route_name = f"Route - {issue.field_name} ({issue.issue_type})"
        nifi_el = _nifi_el_for_issue(issue)
        route_rel_name = f"bad_{issue.field_name}_{issue.issue_type}"[:40]

        route_proc = route_on_attribute_processor(
            name=route_name,
            routes={route_rel_name: nifi_el},
            position_x=200,
            position_y=y,
        )
        processors.append(route_proc)

        # Connect previous to this route
        connections.append(connection(
            prev_unmatched_source,
            route_proc["identifier"],
            prev_unmatched_rel,
            f"to {route_name}",
        ))

        # Fix processor for bad records
        fix_attrs = _fix_attributes_for_issue(issue)
        fix_proc = update_attribute_processor(
            name=f"Fix - {issue.field_name} ({issue.issue_type})",
            attributes=fix_attrs,
            position_x=500,
            position_y=y,
        )
        processors.append(fix_proc)

        # Connect route -> fix (bad records)
        connections.append(connection(
            route_proc["identifier"],
            fix_proc["identifier"],
            [route_rel_name],
            f"bad {issue.field_name}",
        ))

        # Connect fix -> corrected output
        connections.append(connection(
            fix_proc["identifier"],
            corrected_output["identifier"],
            ["success"],
            f"corrected {issue.field_name}",
        ))

        # Unmatched passes to next stage
        prev_unmatched_source = route_proc["identifier"]
        prev_unmatched_rel = ["unmatched"]

    # Connect final unmatched -> valid output
    connections.append(connection(
        prev_unmatched_source,
        valid_output["identifier"],
        prev_unmatched_rel,
        "valid records",
    ))

    # Build the root process group
    group_id = _uuid()

    # Assign groupIdentifier to all components
    _assign_group_ids(processors, group_id)
    _assign_group_ids(connections, group_id)
    _assign_group_ids(controller_services, group_id)

    flow = {
        "flowContents": {
            "identifier": group_id,
            "instanceIdentifier": _uuid(),
            "name": flow_name,
            "comments": "",
            "position": _position(0, 0),
            "processGroups": [],
            "remoteProcessGroups": [],
            "processors": processors,
            "inputPorts": [],
            "outputPorts": [],
            "connections": connections,
            "labels": [],
            "funnels": [],
            "controllerServices": controller_services,
            "variables": {},
            "defaultFlowFileExpiration": "0 sec",
            "defaultBackPressureObjectThreshold": 10000,
            "defaultBackPressureDataSizeThreshold": "1 GB",
            "componentType": "PROCESS_GROUP",
            "flowFileConcurrency": "UNBOUNDED",
            "flowFileOutboundPolicy": "STREAM_WHEN_AVAILABLE",
        },
        "externalControllerServices": {},
        "parameterContexts": {},
        "flowEncodingVersion": "1.0",
        "parameterProviders": {},
        "latest": False,
    }

    return flow


def generate_flow_json(issues: list[QualityIssue], flow_name: str = "AGT Data Quality Remediation") -> str:
    """Generate flow and return as formatted JSON string."""
    flow = generate_flow(issues, flow_name)
    return json.dumps(flow, indent=2)
