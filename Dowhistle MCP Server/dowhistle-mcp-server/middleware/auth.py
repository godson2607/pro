import structlog
from typing import Dict, Any
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.exceptions import ToolError
from config.strings import PROTECTED_TOOL_ERRORS_MESSAGE

logger = structlog.get_logger()



class AuthMiddleware(Middleware):
    """Authorization middleware for protected tools"""
    
    # Define which tools require authentication
    PROTECTED_TOOLS = {
        'toggle_visibility',
        'get_user_profile', 
        'create_whistle',
        'list_whistles'
    }
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Check authentication for protected tools"""
        
        tool_name = context.message.name
        
        # Skip auth for public tools
        if tool_name not in self.PROTECTED_TOOLS:
            return await call_next(context)
        
        # Prefer header-based auth if provided; otherwise check arguments
        access_token = None
        user_id = None

        # Extract from HTTP headers if available (HTTP transport)
        try:
            headers = (context.request.headers if getattr(context, 'request', None) else {}) or {}
            # Normalize header keys to lowercase for safety
            normalized_headers = {str(k).lower(): v for k, v in headers.items()}
            auth_header = normalized_headers.get('authorization')
            if isinstance(auth_header, str) and auth_header.lower().startswith('bearer '):
                access_token = auth_header
            # Optional user id header
            user_id = normalized_headers.get('x-user-id') or None
        except Exception:
            # If any error reading headers, ignore and fall back to args
            pass

        # Fallback to tool arguments
        if not access_token:
            arg_token = context.message.arguments.get('access_token')
            if isinstance(arg_token, str) and arg_token.strip():
                access_token = arg_token.strip()

        # Enforce auth presence and validate token format
        if not access_token or not access_token.lower().startswith('bearer '):
            logger.warning(f"Protected tool accessed without valid token: {tool_name} (token: {access_token})")
            raise ToolError(PROTECTED_TOOL_ERRORS_MESSAGE)

        # Inject discovered values into arguments so downstream tools can rely on them
        # (Only set if not already present to avoid overwriting explicit args)
        context.message.arguments.setdefault('access_token', access_token)
        if user_id and 'user_id' not in context.message.arguments:
            context.message.arguments['user_id'] = user_id

        # Token exists, let backend validate it
        logger.info(f"Token provided for protected tool: {tool_name}")
        return await call_next(context)