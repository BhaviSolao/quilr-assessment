# MCP server with get_customer_record and trigger_refund (stdio)

import json
import logging
import sys

import anyio
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# logs to stderr, stdout is only for json-rpc
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger("customer-server")


class GetCustomerInput(BaseModel):
    # strict so "10" isn't accepted as a number, forbid extra fields
    model_config = ConfigDict(strict=True, extra="forbid")

    customer_id: str = Field(pattern=r"^CUST-\d{5}$")


class RefundInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    customer_id: str = Field(pattern=r"^CUST-\d{5}$")
    amount: float = Field(gt=0)
    reason: str = Field(min_length=10)


CUSTOMERS = {
    "CUST-00001": {"name": "Priya Shah", "tier": "gold"},
    "CUST-12345": {"name": "Rahul Mehta", "tier": "silver"},
}


def get_customer_record(args):
    customer = CUSTOMERS.get(args.customer_id)
    if customer is None:
        return None
    return {"customer_id": args.customer_id, **customer}


def trigger_refund(args):
    if args.customer_id not in CUSTOMERS:
        return None
    log.info("refund of %.2f for %s", args.amount, args.customer_id)
    return {"customer_id": args.customer_id, "amount": args.amount, "status": "refund queued"}


TOOLS = {
    "get_customer_record": (GetCustomerInput, get_customer_record, "Look up a customer by ID (CUST-XXXXX)."),
    "trigger_refund": (RefundInput, trigger_refund, "Refund a customer. Amount > 0, reason 10+ chars."),
}


async def list_tools(ctx, params):
    tools = []
    for name, (model, _, description) in TOOLS.items():
        tools.append(types.Tool(name=name, description=description, inputSchema=model.model_json_schema()))
    return types.ListToolsResult(tools=tools)


async def call_tool(ctx, params):
    if params.name not in TOOLS:
        raise MCPError(INVALID_PARAMS, f"Unknown tool: {params.name}")

    model, function, _ = TOOLS[params.name]

    # bad input -> -32602
    try:
        args = model.model_validate(params.arguments or {})
    except ValidationError as err:
        problems = [{"field": str(e["loc"][0]) if e["loc"] else "", "message": e["msg"]} for e in err.errors()]
        log.info("bad input for %s: %s", params.name, problems)
        raise MCPError(INVALID_PARAMS, "Invalid params", data=problems)

    try:
        result = function(args)
    except Exception:
        log.exception("tool crashed")
        raise MCPError(INTERNAL_ERROR, "Internal error")

    if result is None:
        # valid id but no such customer
        return types.CallToolResult(content=[types.TextContent(type="text", text="Customer not found")], isError=True)

    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(result))])


server = Server("customer-server", on_list_tools=list_tools, on_call_tool=call_tool)


async def main():
    log.info("server starting")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
