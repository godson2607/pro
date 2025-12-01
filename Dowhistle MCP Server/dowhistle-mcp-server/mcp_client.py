#!/usr/bin/env python3
"""
Production-grade MCP Client for testing FastMCP Server
Supports OpenAI integration and comprehensive testing capabilities
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import inquirer
import structlog
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI
from rich.console import Console
from rich_pyfiglet import RichFiglet

console = Console()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Load environment variables
load_dotenv(dotenv_path=".env.dev")


class MCPClientConfig:
    """Configuration for MCP Client"""

    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4")

        # Handle server command configuration with better defaults
        server_cmd = os.getenv("MCP_SERVER_COMMAND", "python main.py --stdio")
        server_args = os.getenv("MCP_SERVER_ARGS", "")

        if server_args:
            self.mcp_server_command = server_cmd
            self.server_args = server_args.split()
        else:
            cmd_parts = server_cmd.split()
            self.mcp_server_command = cmd_parts[0] if cmd_parts else "python"
            self.server_args = (
                cmd_parts[1:] if len(cmd_parts) > 1 else ["main.py", "--stdio"]
            )

        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.connection_timeout = int(os.getenv("MCP_CONNECTION_TIMEOUT", "10"))

    def validate(self) -> bool:
        if not self.openai_api_key:
            click.echo("❌ OPENAI_API_KEY not found in environment", err=True)
            return False
        return True


class MCPClient:
    """Production-grade MCP Client with improved error handling"""

    def __init__(self, config: MCPClientConfig):
        self.config = config
        self.openai_client = (
            AsyncOpenAI(api_key=config.openai_api_key)
            if config.openai_api_key
            else None
        )
        self.session: Optional[ClientSession] = None
        self.stdio_client = None
        self.read = None
        self.write = None
        self.available_tools: List[Dict[str, Any]] = []

    async def __aenter__(self):
        success = await self.connect()
        if not success:
            raise ConnectionError("Failed to connect to MCP server")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    async def connect(self) -> bool:
        try:
            # Check if server file exists
            server_file = (
                Path(self.config.server_args[0])
                if self.config.server_args
                else Path("main.py")
            )
            if not server_file.exists():
                logger.error("Server file not found", file=str(server_file))
                return False

            server_params = StdioServerParameters(
                command=self.config.mcp_server_command,
                args=self.config.server_args,
                env=dict(os.environ),  # Pass current environment
            )

            logger.info(
                "Connecting to MCP server",
                command=self.config.mcp_server_command,
                args=self.config.server_args,
            )

            # Setup stdio transport with timeout
            self.stdio_client = stdio_client(server_params)

            # Use asyncio.wait_for for connection timeout
            try:
                self.read, self.write = await asyncio.wait_for(
                    self.stdio_client.__aenter__(),
                    timeout=self.config.connection_timeout,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "Connection timeout", timeout=self.config.connection_timeout
                )
                return False

            # Create a session with read/write streams
            self.session = ClientSession(self.read, self.write)
            await self.session.__aenter__()

            # Initialize with timeout
            try:
                await asyncio.wait_for(
                    self.session.initialize(), timeout=self.config.connection_timeout
                )

                tools_response = await asyncio.wait_for(
                    self.session.list_tools(), timeout=self.config.connection_timeout
                )
                self.available_tools = tools_response.tools
            except asyncio.TimeoutError:
                logger.error("Initialization timeout")
                return False

            logger.info(
                "Connected to MCP server", tools_count=len(self.available_tools)
            )
            return True

        except Exception as e:
            logger.error("Failed to connect to MCP server", error=str(e))
            # Clean up on failure
            await self.disconnect()
            return False

    async def disconnect(self):
        try:
            if self.session:
                await self.session.__aexit__(None, None, None)
                self.session = None
            if self.stdio_client:
                await self.stdio_client.__aexit__(None, None, None)
                self.stdio_client = None
            logger.info("Disconnected from MCP server")
        except Exception as e:
            logger.error("Error disconnecting from MCP server", error=str(e))

    def get_tools_summary(self) -> str:
        if not self.available_tools:
            return "No tools available"
        summary = []
        for tool in self.available_tools:
            name = tool.name
            desc = tool.description or "No description"
            summary.append(f"• {name}: {desc}")
        return "\n".join(summary)

    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not self.session:
            raise RuntimeError("Not connected to MCP server")
        try:
            logger.info("Calling tool", tool=tool_name, arguments=arguments)

            # Add timeout for tool calls
            result = await asyncio.wait_for(
                self.session.call_tool(tool_name, arguments),
                timeout=30,  # 30 second timeout for tool calls
            )

            logger.info(
                "Tool call successful",
                tool=tool_name,
                result_type=type(result.content).__name__,
            )

            if hasattr(result, "content") and result.content:
                if len(result.content) == 1:
                    content = result.content[0]
                    if hasattr(content, "text"):
                        return {"success": True, "result": content.text}
                    elif hasattr(content, "data"):
                        return {"success": True, "result": content.data}
                return {
                    "success": True,
                    "result": [
                        content.text if hasattr(content, "text") else str(content)
                        for content in result.content
                    ],
                }
            return {"success": True, "result": str(result)}

        except asyncio.TimeoutError:
            logger.error("Tool call timeout", tool=tool_name)
            return {"success": False, "error": "Tool call timeout"}
        except Exception as e:
            logger.error("Tool call failed", tool=tool_name, error=str(e))
            return {"success": False, "error": str(e)}

    async def ai_assisted_action(self, query: str) -> Dict[str, Any]:
        """Generic AI-assisted action that can handle both search and auth tools"""
        if not self.openai_client:
            return {"success": False, "error": "OpenAI client not configured"}

        tools_description = self.get_tools_summary()
        system_prompt = f"""
You are an AI assistant that helps users interact with an MCP server that provides location-based services and authentication.

Available tools:
{tools_description}

Your task is to:
1. Analyze the user's query
2. Determine which tool to call and with what parameters
3. Return a JSON response with the tool name and arguments

For authentication flows, you may need to handle:
- Sign in: Requires phone, country_code, name, location
- OTP verification: Requires user_id and otp_code
- OTP resend: Requires user_id

For search queries, you need latitude, longitude coordinates. If not provided, ask the user.

Always respond with valid JSON in this format:
{{
    "tool_name": "search",
    "arguments": {{
        "latitude": 12.9716,
        "longitude": 77.5946,
        "radius": 2.0,
        "keyword": "restaurant",
        "category": null,
        "limit": 10
    }},
    "reasoning": "Explanation of why you chose these parameters"
}}

If you need more information from the user, respond with:
{{
    "need_input": true,
    "message": "I need your location coordinates to search. Please provide latitude and longitude."
}}
"""
        try:
            response = await self.openai_client.chat.completions.create(
                model=self.config.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            ai_response = response.choices[0].message.content.strip()
            try:
                parsed_response = json.loads(ai_response)
                if parsed_response.get("need_input"):
                    return {
                        "success": False,
                        "needs_input": True,
                        "message": parsed_response.get("message"),
                    }
                tool_name = parsed_response.get("tool_name")
                arguments = parsed_response.get("arguments", {})
                reasoning = parsed_response.get("reasoning", "")
                logger.info(
                    "AI interpreted query",
                    tool=tool_name,
                    arguments=arguments,
                    reasoning=reasoning,
                )
                result = await self.call_tool(tool_name, arguments)
                result["ai_reasoning"] = reasoning
                return result
            except json.JSONDecodeError as e:
                logger.error(
                    "Failed to parse AI response", response=ai_response, error=str(e)
                )
                return {
                    "success": False,
                    "error": f"AI response parsing failed: {str(e)}",
                }
        except Exception as e:
            logger.error("AI-assisted action failed", error=str(e))
            return {"success": False, "error": str(e)}


class MCPClientCLI:
    """CLI Interface for MCP Client"""

    def __init__(self):
        self.config = MCPClientConfig()
        self.client: Optional[MCPClient] = None

    def display_banner(self):
        """Display application banner using pyfiglet"""
        rich_fig = RichFiglet(
            "DoWhistle MCP",
            font="ansi_shadow",
            colors=["#ff0000", "magenta1", "blue3"],
        )
        console.print(rich_fig)
        click.echo("Version 0.1.0".center(80))
        click.echo("=" * 80)
        click.echo("AI-powered command interface for DoWhistle services".center(80))
        click.echo("=" * 80)

    async def interactive_mode(self):
        """Run interactive mode"""
        self.display_banner()

        if not self.config.validate():
            return

        # Try to connect with better error handling
        try:
            click.echo("🔄 Connecting to MCP server...")
            async with MCPClient(self.config) as client:
                self.client = client
                click.echo("✅ Connected successfully!")

                while True:
                    try:
                        choice = inquirer.prompt(
                            [
                                inquirer.List(
                                    "action",
                                    message="What would you like to do?",
                                    choices=[
                                        ("🔍 AI-Assisted Search", "ai_search"),
                                        ("🔐 Authentication Flow", "auth_flow"),
                                        ("📋 List Available Tools", "list_tools"),
                                        ("🔧 Manual Tool Call", "manual_tool"),
                                        ("🔧 Diagnostics", "diagnostics"),
                                        ("❌ Exit", "exit"),
                                    ],
                                )
                            ]
                        )

                        if not choice or choice["action"] == "exit":
                            break

                        await self.handle_action(choice["action"])

                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        click.echo(f"❌ Error: {str(e)}", err=True)

        except ConnectionError as e:
            click.echo(f"❌ Failed to connect to MCP server: {str(e)}")
            await self.show_connection_troubleshooting()
        except Exception as e:
            click.echo(f"❌ Unexpected error: {str(e)}")
            await self.show_connection_troubleshooting()

        click.echo("\n👋 Thank you for using DoWhistle Services. See you soon!")

    async def show_connection_troubleshooting(self):
        """Show connection troubleshooting steps"""
        click.echo("\n🔧 Connection Troubleshooting:")
        click.echo("=" * 50)
        click.echo(
            "1. Make sure your FastMCP server (main.py) is in the current directory"
        )
        click.echo("2. Check your .env file configuration:")
        click.echo("   MCP_SERVER_COMMAND=python main.py --stdio")
        click.echo("   OPENAI_API_KEY=your_key_here")
        click.echo("3. Test if your server runs: python main.py --stdio")
        click.echo("4. Make sure all dependencies are installed")
        click.echo("5. Check that the server supports stdio transport")

        # Offer diagnostics
        run_diagnostics = click.confirm("\nWould you like to run diagnostics?")
        if run_diagnostics:
            await self.run_diagnostics()

    async def handle_action(self, action: str):
        """Handle user action"""
        if action == "ai_search":
            await self.ai_search_flow()
        elif action == "auth_flow":
            await self.auth_flow()
        elif action == "list_tools":
            await self.list_tools_flow()
        elif action == "manual_tool":
            await self.manual_tool_flow()
        elif action == "diagnostics":
            await self.run_diagnostics()

    async def manual_tool_flow(self):
        """Manual tool calling flow"""
        click.echo("\n🔧 Manual Tool Call")
        click.echo("=" * 50)

        if not self.client.available_tools:
            click.echo("❌ No tools available")
            return

        # Select tool
        tool_choices = [
            (f"{tool.name} - {tool.description or 'No description'}", tool.name)
            for tool in self.client.available_tools
        ]

        tool_choice = inquirer.prompt(
            [
                inquirer.List(
                    "tool", message="Select a tool to call:", choices=tool_choices
                )
            ]
        )

        if not tool_choice:
            return

        tool_name = tool_choice["tool"]
        selected_tool = next(
            tool for tool in self.client.available_tools if tool.name == tool_name
        )

        # Show tool schema
        if hasattr(selected_tool, "inputSchema") and selected_tool.inputSchema:
            click.echo(f"\n📋 Tool Schema for '{tool_name}':")
            click.echo(json.dumps(selected_tool.inputSchema, indent=2))

        # Get arguments
        click.echo(f"\n📝 Enter arguments for '{tool_name}' (JSON format):")
        click.echo(
            'Example: {"latitude": 12.9716, "longitude": 77.5946, "keyword": "restaurant"}'
        )

        try:
            args_input = click.prompt("Arguments")
            arguments = json.loads(args_input)

            click.echo("🔄 Calling tool...")
            result = await self.client.call_tool(tool_name, arguments)
            self.display_result(result)

        except json.JSONDecodeError:
            click.echo("❌ Invalid JSON format", err=True)
        except Exception as e:
            click.echo(f"❌ Error: {str(e)}", err=True)

    async def auth_flow(self):
        """NLP-based authentication flow"""
        click.echo("\n🔐 Authentication Flow")
        click.echo("=" * 50)
        click.echo("You can use natural language for authentication actions:")
        click.echo(
            "- Sign in: 'My number is +91 9994076214, name is Paramaswari, location is 10.997, 76.961'"
        )
        click.echo("- Verify OTP: 'Verify my OTP 123456 for user_id abc123'")
        click.echo("- Resend OTP: 'Resend OTP for user_id abc123'")
        click.echo("=" * 50)

        query = click.prompt("Enter your authentication request")

        click.echo("🔄 Processing with AI...")
        result = await self.client.ai_assisted_action(query)

        if result.get("needs_input"):
            click.echo(f"ℹ️  {result.get('message')}")
            return

        self.display_result(result)

    async def ai_search_flow(self):
        """AI-assisted search flow"""
        click.echo("\n🤖 AI-Assisted Search")
        click.echo("=" * 50)

        query = click.prompt(
            "Enter your search query (e.g., 'find restaurants near me')"
        )

        click.echo("🔄 Processing with AI...")
        result = await self.client.ai_assisted_action(query)

        if result.get("needs_input"):
            click.echo(f"ℹ️  {result.get('message')}")
            # Ask for coordinates
            try:
                lat = click.prompt("Enter latitude", type=float)
                lon = click.prompt("Enter longitude", type=float)
                enhanced_query = (
                    f"{query}. Use coordinates: latitude {lat}, longitude {lon}"
                )
                result = await self.client.ai_assisted_action(enhanced_query)
                self.display_result(result)
            except (click.ClickException, ValueError):
                click.echo("❌ Invalid coordinates", err=True)
            return

        self.display_result(result)

    async def list_tools_flow(self):
        """List available tools"""
        click.echo("\n📋 Available Tools")
        click.echo("=" * 50)

        if not self.client.available_tools:
            click.echo("❌ No tools available")
            return

        for i, tool in enumerate(self.client.available_tools, 1):
            click.echo(f"\n{i}. {tool.name}")
            click.echo(f"   Description: {tool.description or 'No description'}")

            if hasattr(tool, "inputSchema") and tool.inputSchema:
                schema = tool.inputSchema
                if "properties" in schema:
                    click.echo("   Parameters:")
                    for prop_name, prop_info in schema["properties"].items():
                        prop_type = prop_info.get("type", "string")
                        description = prop_info.get("description", "No description")
                        required = prop_name in schema.get("required", [])
                        required_mark = " *" if required else ""
                        click.echo(
                            f"     • {prop_name} ({prop_type}){required_mark}: {description}"
                        )

    async def run_diagnostics(self):
        """Run diagnostic checks"""
        click.echo("\n🔧 Running Diagnostics")
        click.echo("=" * 50)

        # Check Python
        click.echo(f"✅ Python version: {sys.version.split()[0]}")
        click.echo(f"✅ Python executable: {sys.executable}")

        # Check current directory
        current_dir = Path.cwd()
        click.echo(f"📁 Current directory: {current_dir}")

        # Check for main.py
        main_py_path = current_dir / "main.py"
        if main_py_path.exists():
            click.echo("✅ main.py found in current directory")
        else:
            click.echo("❌ main.py not found in current directory")

            # Look for it elsewhere
            for py_file in current_dir.glob("**/*.py"):
                if py_file.name == "main.py":
                    click.echo(f"💡 Found main.py at: {py_file}")
                    break

        # Check configuration
        click.echo(f"\n⚙️  Configuration:")
        click.echo(f"   Server Command: {self.config.mcp_server_command}")
        click.echo(f"   Server Args: {self.config.server_args}")
        click.echo(
            f"   OpenAI Key: {'✅ Set' if self.config.openai_api_key else '❌ Not set'}"
        )
        click.echo(f"   Connection Timeout: {self.config.connection_timeout}s")

        # Check if command is available
        import shutil

        cmd_available = shutil.which(self.config.mcp_server_command)
        if cmd_available:
            click.echo(
                f"✅ Command '{self.config.mcp_server_command}' found at: {cmd_available}"
            )
        else:
            click.echo(f"❌ Command '{self.config.mcp_server_command}' not found")

            # Suggest alternatives
            alternatives = ["python", "python3", "py", sys.executable]
            click.echo("💡 Available Python interpreters:")
            for alt in alternatives:
                alt_path = shutil.which(alt)
                if alt_path:
                    click.echo(f"   • {alt}: {alt_path}")

        # Test server command
        click.echo(f"\n🧪 Testing server command...")
        try:
            import subprocess

            # First try with --help
            result = subprocess.run(
                [self.config.mcp_server_command, "--help"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                click.echo("✅ Server command responds to --help")
            else:
                click.echo("⚠️  Server command doesn't support --help")

            # Then try to run with actual args for a brief moment
            click.echo("🧪 Testing actual server startup...")
            process = subprocess.Popen(
                [self.config.mcp_server_command] + self.config.server_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            try:
                stdout, stderr = process.communicate(timeout=3)
                click.echo(f"✅ Server started (exit code: {process.returncode})")
                if stdout:
                    click.echo(f"📤 Stdout: {stdout[:200]}...")
                if stderr:
                    click.echo(f"📥 Stderr: {stderr[:200]}...")
            except subprocess.TimeoutExpired:
                process.terminate()
                click.echo("✅ Server appears to be running (killed after 3s)")

        except subprocess.TimeoutExpired:
            click.echo("⚠️  Server command timeout (might be waiting for input)")
        except Exception as e:
            click.echo(f"❌ Error testing server command: {str(e)}")

        # Check dependencies
        click.echo(f"\n📦 Checking dependencies...")
        required_packages = ["fastmcp", "mcp", "openai", "aiohttp"]
        for package in required_packages:
            try:
                __import__(package)
                click.echo(f"✅ {package} installed")
            except ImportError:
                click.echo(f"❌ {package} not installed")

        # Suggest fixes
        click.echo(f"\n💡 Suggested fixes:")
        if not main_py_path.exists():
            click.echo("1. Make sure main.py is in the current directory")
            click.echo("2. Or update MCP_SERVER_COMMAND in .env with full path")

        if not cmd_available:
            click.echo("3. Update MCP_SERVER_COMMAND in .env file:")
            for alt in ["python", "python3", "py"]:
                alt_path = shutil.which(alt)
                if alt_path:
                    click.echo(f"   MCP_SERVER_COMMAND={alt} main.py --stdio")
                    break

        if not self.config.openai_api_key:
            click.echo("4. Add OpenAI API key to .env file for AI features")

        click.echo("5. Make sure your .env file contains:")
        click.echo("   MCP_SERVER_COMMAND=python main.py --stdio")
        click.echo("   OPENAI_API_KEY=your_key_here")

    def display_result(self, result: Dict[str, Any]):
        """Display formatted result"""
        click.echo("\n📄 Result")
        click.echo("=" * 30)

        if result.get("success"):
            click.echo("✅ Success")

            if result.get("ai_reasoning"):
                click.echo(f"🤖 AI Reasoning: {result['ai_reasoning']}")

            result_data = result.get("result")
            if isinstance(result_data, str):
                try:
                    # Try to parse as JSON for better formatting
                    parsed = json.loads(result_data)
                    click.echo(json.dumps(parsed, indent=2))
                except json.JSONDecodeError:
                    click.echo(result_data)
            else:
                click.echo(json.dumps(result_data, indent=2, default=str))
        else:
            click.echo("❌ Failed")
            click.echo(f"Error: {result.get('error', 'Unknown error')}")


# CLI Commands
@click.group()
@click.option("--log-level", default="INFO", help="Set log level")
def cli(log_level):
    """MCP Client - Production Grade Testing Tool"""
    structlog.configure()


@cli.command()
def interactive():
    """Run in interactive mode"""
    cli_app = MCPClientCLI()
    asyncio.run(cli_app.interactive_mode())


@cli.command()
@click.option("--query", required=True, help="Search query")
def search(query):
    """AI-assisted search"""

    async def run_search():
        config = MCPClientConfig()
        if not config.validate():
            return

        try:
            async with MCPClient(config) as client:
                result = await client.ai_assisted_action(query)
                if result.get("success"):
                    click.echo(json.dumps(result.get("result"), indent=2))
                else:
                    click.echo(f"Error: {result.get('error')}", err=True)
        except Exception as e:
            click.echo(f"Connection error: {str(e)}", err=True)

    asyncio.run(run_search())


@cli.command()
def auth():
    """NLP-based authentication flow"""

    async def run_auth():
        cli_app = MCPClientCLI()
        config = MCPClientConfig()
        if not config.validate():
            return

        try:
            async with MCPClient(config) as client:
                cli_app.client = client
                await cli_app.auth_flow()
        except Exception as e:
            click.echo(f"Connection error: {str(e)}", err=True)

    asyncio.run(run_auth())


@cli.command()
def test_connection():
    """Test connection to MCP server"""

    async def run_test():
        config = MCPClientConfig()
        click.echo("🔄 Testing connection to MCP server...")

        try:
            async with MCPClient(config) as client:
                click.echo("✅ Connection successful!")
                click.echo(f"📋 Available tools: {len(client.available_tools)}")
                for tool in client.available_tools:
                    click.echo(
                        f"   • {tool.name}: {tool.description or 'No description'}"
                    )
        except Exception as e:
            click.echo(f"❌ Connection failed: {str(e)}", err=True)
            cli_app = MCPClientCLI()
            await cli_app.show_connection_troubleshooting()

    asyncio.run(run_test())


@cli.command()
def diagnostics():
    """Run diagnostic checks"""

    async def run_diagnostics():
        cli_app = MCPClientCLI()
        await cli_app.run_diagnostics()

    asyncio.run(run_diagnostics())


if __name__ == "__main__":
    cli()
