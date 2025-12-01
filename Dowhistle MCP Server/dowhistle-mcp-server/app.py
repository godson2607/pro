import structlog
from fastmcp import FastMCP
from starlette.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from agents.search import SearchAgent
from agents.auth import AuthAgent
from agents.whistle import WhistleAgent
from agents.user import UserAgent
from middleware.auth import AuthMiddleware
from middleware.logging import LoggingMiddleware
from middleware.rate_limit import RateLimitMiddleware
from config.settings import settings
from dotenv import load_dotenv

load_dotenv()
# Configure structured logging for production
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer() if settings.ENVIRONMENT == "production" 
        else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

def create_app():
    """Create and configure production-grade MCP server"""
    
    mcp = FastMCP("Whistle MCP Server")
    
    # Add middleware in correct order (first added = outermost layer)
    mcp.add_middleware(LoggingMiddleware())    # Log everything first
    mcp.add_middleware(RateLimitMiddleware())  # Rate limit before processing
    mcp.add_middleware(AuthMiddleware())      # Check auth before execution
    
    # Register all agents
    SearchAgent(mcp)
    AuthAgent(mcp)
    WhistleAgent(mcp)
    UserAgent(mcp)
    
    # Health check endpoint
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request):
        return JSONResponse({
            "status": "healthy",
            "service": "whistle-mcp-server",
            "environment": settings.ENVIRONMENT,
            "version": "1.0.0",
            "middleware": ["logging", "rate_limit", "auth"]
        })
    
    # Metrics endpoint for monitoring
    @mcp.custom_route("/metrics", methods=["GET"])
    async def metrics(request):
        return JSONResponse({
            "status": "ok",
            "message": "Metrics endpoint ready for monitoring integration"
        })
    
    # Get the ASGI app
    app = mcp.http_app(stateless_http=True)
    
    # Add CORS middleware for development
    if settings.ENVIRONMENT == "development":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    logger.info(
        "Production MCP server created",
        environment=settings.ENVIRONMENT,
        middleware_count=3,
        agents_count=4
    )
    
    return app

# Create the ASGI app
app = create_app()
