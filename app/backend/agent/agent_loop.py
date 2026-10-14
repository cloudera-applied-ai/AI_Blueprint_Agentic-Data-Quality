"""Iterative tool-calling agent loop with SSE streaming support.

Includes content-based tool call extraction for LLMs that output tool calls
as text content instead of using the proper tool_calls mechanism (common with
smaller models like qwen2.5 via Ollama).
"""

import json
import re
import uuid
from typing import AsyncGenerator

import duckdb
from openai import OpenAI

import config
from data.metadata import FieldMeta
from agent.llm_client import chat_completion
from agent.tools import TOOL_DEFINITIONS, execute_tool
from agent.prompts import build_system_prompt, build_fields_table
from routers.data import get_db_lock

# Tool names the agent can call
_VALID_TOOL_NAMES = {t["function"]["name"] for t in TOOL_DEFINITIONS}


def _extract_tool_from_content(text: str) -> dict | None:
    """Try to extract a tool call from LLM text that looks like a JSON tool call.

    Some LLMs (especially smaller ones) output tool calls as text content
    instead of using the proper function-calling mechanism. This detects
    patterns like:
        {"name": "detect_quality_issues", "parameters": {"field_names": []}}
        {"type": "function", "function": "detect_quality_issues", ...}
    and extracts the tool name and arguments.
    """
    stripped = text.strip()

    # Only try extraction if the response looks like JSON (starts with {)
    if not stripped.startswith("{"):
        return None

    # Also detect when the model fabricates a NiFi flow as a JSON array
    if stripped.startswith("[") and '"type"' in stripped[:200] and '"name"' in stripped[:200]:
        return None  # This is fabricated content, not a tool call

    # Try to extract tool name and args from various malformed patterns
    # Pattern 1: {"name": "tool_name", "parameters": {...}}
    # Pattern 2: {"type": "function", "function": "tool_name", "parameters": {...}}
    # Pattern 3: {"name": "tool_name", "parameters{...}} (missing colon)

    tool_name = None
    tool_args = {}

    # Try to find a tool name in the text
    for name in _VALID_TOOL_NAMES:
        if name in stripped:
            tool_name = name
            break

    if not tool_name:
        return None

    # Try to extract arguments - look for common parameter names
    # For detect_quality_issues
    if tool_name == "detect_quality_issues":
        field_match = re.search(r'"field_names"\s*:\s*\[(.*?)\]', stripped)
        if field_match:
            raw = field_match.group(1).strip()
            if raw and raw != '""' and raw != '"*"' and raw != '""':
                names = [s.strip().strip('"').strip("'") for s in raw.split(",") if s.strip().strip('"').strip("'")]
                tool_args = {"field_names": names}
            else:
                tool_args = {"field_names": []}
        else:
            tool_args = {"field_names": []}

    # For profile_column
    elif tool_name == "profile_column":
        field_match = re.search(r'"field_name"\s*:\s*"([^"]*)"', stripped)
        if field_match:
            tool_args = {"field_name": field_match.group(1)}
        else:
            return None  # Can't profile without a field name

    # For run_sql_query
    elif tool_name == "run_sql_query":
        sql_match = re.search(r'"sql"\s*:\s*"((?:[^"\\]|\\.)*)"', stripped)
        if sql_match:
            tool_args = {"sql": sql_match.group(1)}
        else:
            return None

    # For generate_nifi_flow
    elif tool_name == "generate_nifi_flow":
        desc_match = re.search(r'"issue_descriptions"\s*:\s*\[(.*?)\]', stripped, re.DOTALL)
        if desc_match:
            raw = desc_match.group(1).strip()
            descs = [s.strip().strip('"').strip("'") for s in raw.split(",") if s.strip().strip('"').strip("'")]
            tool_args = {"issue_descriptions": descs}
        else:
            tool_args = {"issue_descriptions": []}
        name_match = re.search(r'"flow_name"\s*:\s*"([^"]*)"', stripped)
        if name_match:
            tool_args["flow_name"] = name_match.group(1)

    # For generate_spark_job
    elif tool_name == "generate_spark_job":
        desc_match = re.search(r'"issue_descriptions"\s*:\s*\[(.*?)\]', stripped, re.DOTALL)
        if desc_match:
            raw = desc_match.group(1).strip()
            descs = [s.strip().strip('"').strip("'") for s in raw.split(",") if s.strip().strip('"').strip("'")]
            tool_args = {"issue_descriptions": descs}
        else:
            tool_args = {"issue_descriptions": []}
        name_match = re.search(r'"job_name"\s*:\s*"([^"]*)"', stripped)
        if name_match:
            tool_args["job_name"] = name_match.group(1)
        fmt_match = re.search(r'"output_format"\s*:\s*"([^"]*)"', stripped)
        if fmt_match:
            tool_args["output_format"] = fmt_match.group(1)

    # For generate_metadata_yaml
    elif tool_name == "generate_metadata_yaml":
        desc_match = re.search(r'"issue_descriptions"\s*:\s*\[(.*?)\]', stripped, re.DOTALL)
        if desc_match:
            raw = desc_match.group(1).strip()
            descs = [s.strip().strip('"').strip("'") for s in raw.split(",") if s.strip().strip('"').strip("'")]
            tool_args = {"issue_descriptions": descs}
        else:
            tool_args = {"issue_descriptions": []}
        name_match = re.search(r'"spec_name"\s*:\s*"([^"]*)"', stripped)
        if name_match:
            tool_args["spec_name"] = name_match.group(1)

    # For get_data_summary
    elif tool_name == "get_data_summary":
        tool_args = {}

    # For get_field_metadata
    elif tool_name == "get_field_metadata":
        field_match = re.search(r'"field_names"\s*:\s*\[(.*?)\]', stripped)
        if field_match:
            raw = field_match.group(1).strip()
            names = [s.strip().strip('"').strip("'") for s in raw.split(",") if s.strip().strip('"').strip("'")]
            tool_args = {"field_names": names}
        else:
            tool_args = {"field_names": []}

    # For validate_coded_values
    elif tool_name == "validate_coded_values":
        field_match = re.search(r'"field_name"\s*:\s*"([^"]*)"', stripped)
        vals_match = re.search(r'"valid_values"\s*:\s*\[(.*?)\]', stripped)
        if field_match and vals_match:
            vals = [s.strip().strip('"').strip("'") for s in vals_match.group(1).split(",") if s.strip().strip('"').strip("'")]
            tool_args = {"field_name": field_match.group(1), "valid_values": vals}
        else:
            return None

    return {"name": tool_name, "arguments": tool_args}


def _looks_like_fabricated_flow(text: str) -> bool:
    """Detect when the LLM fabricates a NiFi flow as plain text instead of calling the tool."""
    indicators = [
        '"type": "GetFile"',
        '"type": "PutFile"',
        '"type": "RouteOnAttribute"',
        '"type": "UpdateAttribute"',
        "GetFile - Input",
        "PutFile - Valid",
        "PutFile - Corrected",
        "PutFile - Rejected",
        "Route -",
        "Fix -",
    ]
    count = sum(1 for pattern in indicators if pattern in text)
    return count >= 3


def _looks_like_fabricated_yaml(text: str) -> bool:
    """Detect when the LLM fabricates a YAML metadata spec instead of calling the tool."""
    indicators = [
        "metadata:",
        "fields:",
        "rules:",
        "valid_value_sets:",
        "issue_type:",
        "severity:",
        "remediation:",
        "affected_count:",
        "affected_pct:",
    ]
    count = sum(1 for pattern in indicators if pattern in text)
    return count >= 5


def _looks_like_fabricated_spark(text: str) -> bool:
    """Detect when the LLM fabricates PySpark remediation code instead of calling the tool."""
    indicators = [
        "SparkSession.builder",
        "_has_quality_issue",
        "_flag_",
        "F.when(",
        ".withColumn(",
        'write.mode("overwrite")',
        "valid_df",
        "corrected_df",
        "rejected_df",
    ]
    count = sum(1 for pattern in indicators if pattern in text)
    return count >= 4


def run_agent(
    client: OpenAI,
    model: str,
    user_messages: list[dict],
    conn: duckdb.DuckDBPyConnection,
    fields: list[FieldMeta],
    row_count: int | None = None,
    issues_cache: list | None = None,
) -> dict:
    """Run the agent loop synchronously.

    Returns dict with:
        - "response": final text response
        - "tool_calls": list of {name, arguments, result} for each tool invocation
    """
    fields_table = build_fields_table(fields)
    system_msg = {"role": "system", "content": build_system_prompt(fields_table, row_count)}

    messages = [system_msg] + user_messages
    tool_call_log = []

    for _ in range(config.MAX_AGENT_ITERATIONS):
        response = chat_completion(client, model, messages, TOOL_DEFINITIONS)
        choice = response.choices[0]

        if choice.finish_reason == "tool_calls" or choice.message.tool_calls:
            # Append the assistant message with tool calls
            messages.append(choice.message.model_dump())

            for tc in choice.message.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}
                    error_msg = json.dumps({
                        "error": f"Malformed JSON in arguments for {fn_name}. "
                                 "Please retry with valid JSON. Arguments must be "
                                 "a JSON object, e.g. {\"issue_descriptions\": [\"invalid phone numbers\"]}"
                    })
                    tool_call_log.append({
                        "name": fn_name,
                        "arguments": fn_args,
                        "result": error_msg,
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": error_msg,
                    })
                    continue

                with get_db_lock():
                    result = execute_tool(fn_name, fn_args, conn, fields, issues_cache)

                tool_call_log.append({
                    "name": fn_name,
                    "arguments": fn_args,
                    "result": result,
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
        else:
            text = choice.message.content or ""

            # Check if the LLM output a tool call as text instead of using function calling
            extracted = _extract_tool_from_content(text)
            if extracted:
                # Execute the intended tool call
                fake_tc_id = f"rescued_{uuid.uuid4().hex[:8]}"
                messages.append({"role": "assistant", "content": None, "tool_calls": [{
                    "id": fake_tc_id,
                    "type": "function",
                    "function": {"name": extracted["name"], "arguments": json.dumps(extracted["arguments"])},
                }]})

                with get_db_lock():
                    result = execute_tool(extracted["name"], extracted["arguments"], conn, fields, issues_cache)
                tool_call_log.append({
                    "name": extracted["name"],
                    "arguments": extracted["arguments"],
                    "result": result,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": fake_tc_id,
                    "content": result,
                })
                # Continue the loop so LLM can process the tool result
                continue

            # Check if the LLM fabricated a NiFi flow
            if _looks_like_fabricated_flow(text):
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": (
                    "That NiFi flow is not correct — it was not generated by the system. "
                    "Please call the generate_nifi_flow tool to produce a real NiFi v2 flow. "
                    "Do NOT write NiFi JSON yourself."
                )})
                continue

            # Check if the LLM fabricated PySpark code
            if _looks_like_fabricated_spark(text):
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": (
                    "That PySpark script is not correct — it was not generated by the system. "
                    "Please call the generate_spark_job tool to produce a real CDE Spark job. "
                    "Do NOT write PySpark remediation code yourself."
                )})
                continue

            # Check if the LLM fabricated YAML metadata
            if _looks_like_fabricated_yaml(text):
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": (
                    "That YAML metadata spec is not correct — it was not generated by the system. "
                    "Please call the generate_metadata_yaml tool to produce a real metadata spec. "
                    "Do NOT write YAML metadata yourself."
                )})
                continue

            # Normal text response
            return {
                "response": text,
                "tool_calls": tool_call_log,
            }

    # Max iterations reached
    return {
        "response": "I've reached the maximum number of analysis steps. Here's what I found so far based on the tool results above.",
        "tool_calls": tool_call_log,
    }


async def run_agent_stream(
    client: OpenAI,
    model: str,
    user_messages: list[dict],
    conn: duckdb.DuckDBPyConnection,
    fields: list[FieldMeta],
    row_count: int | None = None,
    issues_cache: list | None = None,
) -> AsyncGenerator[dict, None]:
    """Run agent loop yielding SSE events.

    Yields dicts with "event" and "data" keys:
        - {"event": "tool_call", "data": {"name": ..., "arguments": ...}}
        - {"event": "tool_result", "data": {"name": ..., "result": ...}}
        - {"event": "content", "data": {"text": ...}}
        - {"event": "done", "data": {}}
        - {"event": "error", "data": {"message": ...}}
    """
    fields_table = build_fields_table(fields)
    system_msg = {"role": "system", "content": build_system_prompt(fields_table, row_count)}

    messages = [system_msg] + user_messages

    try:
        for _ in range(config.MAX_AGENT_ITERATIONS):
            response = chat_completion(client, model, messages, TOOL_DEFINITIONS)
            choice = response.choices[0]

            if choice.finish_reason == "tool_calls" or choice.message.tool_calls:
                messages.append(choice.message.model_dump())

                for tc in choice.message.tool_calls:
                    fn_name = tc.function.name
                    try:
                        fn_args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        fn_args = {}
                        error_msg = json.dumps({
                            "error": f"Malformed JSON in arguments for {fn_name}. "
                                     "Please retry with valid JSON."
                        })
                        yield {"event": "tool_call", "data": {"name": fn_name, "arguments": fn_args}}
                        yield {"event": "tool_result", "data": {"name": fn_name, "result": error_msg}}
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": error_msg,
                        })
                        continue

                    yield {"event": "tool_call", "data": {"name": fn_name, "arguments": fn_args}}

                    with get_db_lock():
                        result = execute_tool(fn_name, fn_args, conn, fields, issues_cache)

                    yield {"event": "tool_result", "data": {"name": fn_name, "result": result}}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
            else:
                text = choice.message.content or ""

                # Check if the LLM output a tool call as text
                extracted = _extract_tool_from_content(text)
                if extracted:
                    fake_tc_id = f"rescued_{uuid.uuid4().hex[:8]}"
                    messages.append({"role": "assistant", "content": None, "tool_calls": [{
                        "id": fake_tc_id,
                        "type": "function",
                        "function": {"name": extracted["name"], "arguments": json.dumps(extracted["arguments"])},
                    }]})

                    yield {"event": "tool_call", "data": {"name": extracted["name"], "arguments": extracted["arguments"]}}

                    with get_db_lock():
                        result = execute_tool(extracted["name"], extracted["arguments"], conn, fields, issues_cache)

                    yield {"event": "tool_result", "data": {"name": extracted["name"], "result": result}}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": fake_tc_id,
                        "content": result,
                    })
                    # Continue the loop so LLM can process the tool result
                    continue

                # Check if the LLM fabricated a NiFi flow
                if _looks_like_fabricated_flow(text):
                    messages.append({"role": "assistant", "content": text})
                    messages.append({"role": "user", "content": (
                        "That NiFi flow is not correct. Please call the generate_nifi_flow tool instead. "
                        "Do NOT write NiFi JSON yourself."
                    )})
                    continue

                # Check if the LLM fabricated PySpark code
                if _looks_like_fabricated_spark(text):
                    messages.append({"role": "assistant", "content": text})
                    messages.append({"role": "user", "content": (
                        "That PySpark script is not correct. Please call the generate_spark_job tool instead. "
                        "Do NOT write PySpark remediation code yourself."
                    )})
                    continue

                # Check if the LLM fabricated YAML metadata
                if _looks_like_fabricated_yaml(text):
                    messages.append({"role": "assistant", "content": text})
                    messages.append({"role": "user", "content": (
                        "That YAML metadata spec is not correct. Please call the generate_metadata_yaml tool instead. "
                        "Do NOT write YAML metadata yourself."
                    )})
                    continue

                yield {"event": "content", "data": {"text": text}}
                yield {"event": "done", "data": {}}
                return

        yield {"event": "content", "data": {"text": "Reached maximum analysis steps."}}
        yield {"event": "done", "data": {}}

    except Exception as e:
        yield {"event": "error", "data": {"message": str(e)}}
