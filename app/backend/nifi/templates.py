"""NiFi v2 processor and component configuration templates."""

import uuid

BUNDLE = {
    "group": "org.apache.nifi",
    "artifact": "nifi-standard-nar",
    "version": "2.0.0",
}

BUNDLE_RECORD = {
    "group": "org.apache.nifi",
    "artifact": "nifi-record-serialization-services-nar",
    "version": "2.0.0",
}

BUNDLE_RECORD_API = {
    "group": "org.apache.nifi",
    "artifact": "nifi-standard-services-api-nar",
    "version": "2.0.0",
}

# Default scheduling values matching NiFi 2.0 defaults
_PROCESSOR_DEFAULTS = {
    "comments": "",
    "style": {},
    "schedulingPeriod": "0 sec",
    "schedulingStrategy": "TIMER_DRIVEN",
    "executionNode": "ALL",
    "penaltyDuration": "30 sec",
    "yieldDuration": "1 sec",
    "bulletinLevel": "WARN",
    "runDurationMillis": 0,
    "concurrentlySchedulableTaskCount": 1,
    "retryCount": 10,
    "retriedRelationships": [],
    "backoffMechanism": "PENALIZE_FLOWFILE",
    "maxBackoffPeriod": "10 mins",
    "componentType": "PROCESSOR",
}


def _uuid() -> str:
    return str(uuid.uuid4())


def _position(x: int = 0, y: int = 0) -> dict:
    return {"x": float(x), "y": float(y)}


def _processor(
    name: str,
    proc_type: str,
    bundle: dict,
    properties: dict,
    position_x: int = 0,
    position_y: int = 0,
    auto_terminated: list[str] | None = None,
    scheduled_state: str = "ENABLED",
) -> dict:
    """Build a complete NiFi 2.0 processor definition with all required fields."""
    proc = {
        "identifier": _uuid(),
        "instanceIdentifier": _uuid(),
        "name": name,
        "type": proc_type,
        "bundle": bundle,
        "properties": properties,
        "propertyDescriptors": {},
        "autoTerminatedRelationships": auto_terminated or [],
        "scheduledState": scheduled_state,
        "position": _position(position_x, position_y),
    }
    proc.update(_PROCESSOR_DEFAULTS)
    return proc


def csv_reader_service(delimiter: str = "|") -> dict:
    return {
        "identifier": _uuid(),
        "instanceIdentifier": _uuid(),
        "name": "CSVReader",
        "comments": "",
        "type": "org.apache.nifi.csv.CSVReader",
        "bundle": BUNDLE_RECORD,
        "properties": {
            "csv-reader-csv-parser": "commons-csv",
            "Value Separator": delimiter,
            "Skip Header Line": "false",
            "Schema Access Strategy": "csv-header-derived",
        },
        "propertyDescriptors": {},
        "controllerServiceApis": [{
            "type": "org.apache.nifi.serialization.RecordReaderFactory",
            "bundle": BUNDLE_RECORD_API,
        }],
        "scheduledState": "ENABLED",
        "bulletinLevel": "WARN",
        "componentType": "CONTROLLER_SERVICE",
    }


def csv_writer_service(delimiter: str = "|") -> dict:
    return {
        "identifier": _uuid(),
        "instanceIdentifier": _uuid(),
        "name": "CSVRecordSetWriter",
        "comments": "",
        "type": "org.apache.nifi.csv.CSVRecordSetWriter",
        "bundle": BUNDLE_RECORD,
        "properties": {
            "Value Separator": delimiter,
            "Include Header Line": "true",
            "Schema Write Strategy": "full-schema-attribute",
        },
        "propertyDescriptors": {},
        "controllerServiceApis": [{
            "type": "org.apache.nifi.serialization.RecordSetWriterFactory",
            "bundle": BUNDLE_RECORD_API,
        }],
        "scheduledState": "ENABLED",
        "bulletinLevel": "WARN",
        "componentType": "CONTROLLER_SERVICE",
    }


def get_file_processor(input_dir: str = "/data/input") -> dict:
    return _processor(
        name="GetFile - Input",
        proc_type="org.apache.nifi.processors.standard.GetFile",
        bundle=BUNDLE,
        properties={
            "Input Directory": input_dir,
            "File Filter": "[^\\.].*\\.txt",
            "Keep Source File": "false",
        },
        position_x=0,
        position_y=0,
    )


def route_on_attribute_processor(
    name: str,
    routes: dict[str, str],
    position_x: int = 0,
    position_y: int = 0,
) -> dict:
    """RouteOnAttribute with NiFi Expression Language conditions.

    routes: dict of route_name -> NiFi EL expression
    e.g. {"invalid_phone": "${PRMRYPHONENBR:matches('^[01].*')}"}
    """
    props = {"Routing Strategy": "Route to Property name"}
    props.update(routes)

    return _processor(
        name=name,
        proc_type="org.apache.nifi.processors.standard.RouteOnAttribute",
        bundle=BUNDLE,
        properties=props,
        position_x=position_x,
        position_y=position_y,
    )


def update_attribute_processor(
    name: str,
    attributes: dict[str, str],
    position_x: int = 0,
    position_y: int = 0,
) -> dict:
    return _processor(
        name=name,
        proc_type="org.apache.nifi.processors.standard.UpdateAttribute",
        bundle=BUNDLE,
        properties=attributes,
        position_x=position_x,
        position_y=position_y,
    )


def validate_record_processor(
    name: str,
    reader_id: str,
    writer_id: str,
    position_x: int = 0,
    position_y: int = 0,
) -> dict:
    return _processor(
        name=name,
        proc_type="org.apache.nifi.processors.standard.ValidateRecord",
        bundle=BUNDLE,
        properties={
            "record-reader": reader_id,
            "record-writer": writer_id,
            "Schema Access Strategy": "csv-header-derived",
            "Allow Extra Fields": "true",
            "Strict Type Checking": "false",
        },
        position_x=position_x,
        position_y=position_y,
    )


def put_file_processor(
    name: str,
    output_dir: str,
    position_x: int = 0,
    position_y: int = 0,
) -> dict:
    return _processor(
        name=name,
        proc_type="org.apache.nifi.processors.standard.PutFile",
        bundle=BUNDLE,
        properties={
            "Directory": output_dir,
            "Conflict Resolution Strategy": "replace",
        },
        auto_terminated=["failure"],
        position_x=position_x,
        position_y=position_y,
    )


def connection(
    source_id: str,
    dest_id: str,
    relationships: list[str],
    name: str = "",
) -> dict:
    return {
        "identifier": _uuid(),
        "instanceIdentifier": _uuid(),
        "name": name,
        "source": {
            "id": source_id,
            "type": "PROCESSOR",
            "groupId": "",
            "name": "",
            "comments": "",
        },
        "destination": {
            "id": dest_id,
            "type": "PROCESSOR",
            "groupId": "",
            "name": "",
            "comments": "",
        },
        "selectedRelationships": relationships,
        "backPressureObjectThreshold": 10000,
        "backPressureDataSizeThreshold": "1 GB",
        "flowFileExpiration": "0 sec",
        "prioritizers": [],
        "bends": [],
        "labelIndex": 1,
        "zIndex": 0,
        "loadBalanceStrategy": "DO_NOT_LOAD_BALANCE",
        "partitioningAttribute": "",
        "loadBalanceCompression": "DO_NOT_COMPRESS",
        "componentType": "CONNECTION",
    }
