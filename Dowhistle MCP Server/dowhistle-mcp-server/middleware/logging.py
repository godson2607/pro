import structlog
import time
from typing import Dict, Any
from fastmcp.server.middleware import Middleware, MiddlewareContext

logger = structlog.get_logger()

class LoggingMiddleware(Middleware):
    """Enhanced logging middleware for production monitoring"""
    
    async def on_message(self, context: MiddlewareContext, call_next):
        """Log all MCP messages with performance metrics"""
        
        start_time = time.perf_counter()
        
        # Sanitize sensitive data for logging
        safe_context = self._get_safe_log_context(context)
        
        logger.info(
            "MCP message started",
            method=context.method,
            source=context.source,
            type=context.type,
            **safe_context
        )
        
        try:
            result = await call_next(context)
            
            execution_time = (time.perf_counter() - start_time) * 1000
            
            logger.info(
                "MCP message completed",
                method=context.method,
                execution_time_ms=round(execution_time, 2),
                success=True
            )
            
            return result
            
        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            
            logger.error(
                "MCP message failed",
                method=context.method,
                error=str(e),
                error_type=type(e).__name__,
                execution_time_ms=round(execution_time, 2)
            )
            
            raise
    
    def _get_safe_log_context(self, context: MiddlewareContext) -> Dict[str, Any]:
        """Extract safe logging context, removing sensitive data"""
        
        safe_context = {}
        
        # Add tool name for tool calls
        if hasattr(context.message, 'name'):
            safe_context['tool_name'] = context.message.name
        
        # Add sanitized arguments for tool calls
        if hasattr(context.message, 'arguments') and context.message.arguments:
            safe_args = self._sanitize_arguments(context.message.arguments)
            safe_context['argument_keys'] = list(safe_args.keys())
            safe_context['has_auth_token'] = bool(context.message.arguments.get('access_token'))
        
        return safe_context
    
    def _sanitize_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive information from arguments"""
        
        safe_args = arguments.copy()
        
        # Remove or mask sensitive fields
        sensitive_fields = ['access_token', 'otp_code', 'phone']
        
        for field in sensitive_fields:
            if field in safe_args:
                if field == 'access_token':
                    # Show only last 4 characters
                    token = safe_args[field]
                    safe_args[field] = f"***{token[-4:]}" if len(token) > 4 else "***"
                elif field == 'phone':
                    # Mask middle digits
                    phone = safe_args[field]
                    safe_args[field] = f"{phone[:2]}***{phone[-2:]}" if len(phone) > 4 else "***"
                else:
                    safe_args[field] = "***"
        
        return safe_args
