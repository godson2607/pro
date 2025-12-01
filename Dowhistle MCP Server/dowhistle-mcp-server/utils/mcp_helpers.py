from fastmcp import FastMCP

def get_tool(mcp: FastMCP, name: str):
    """
    Public accessor for MCP tools.
    Wraps the private _tools dict so tests and code
    never touch internals directly.
    """
    try:
        return mcp._tools[name]
    except KeyError:
        raise ValueError(f"Tool '{name}' not registered in MCP instance")
