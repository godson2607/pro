import time
import structlog
from typing import DefaultDict
from collections import defaultdict
from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp import McpError
from mcp.types import ErrorData

logger = structlog.get_logger()

class RateLimitMiddleware(Middleware):
    """Rate limiting middleware for production protection"""
    
    def __init__(self):
        # Simple in-memory rate limiting (use Redis for production scale)
        self.request_counts: DefaultDict[str, list] = defaultdict(list)
        
        # Rate limits per tool (requests per minute)
        self.rate_limits = {
            'search_businesses': 30,  # 30 requests per minute
            'sign_in': 5,            # 5 sign in attempts per minute
            'verify_otp': 10,        # 10 OTP verifications per minute
            'resend_otp': 3,         # 3 resend requests per minute
            'create_whistle': 20,    # 20 whistles per minute
            'toggle_visibility': 10,  # 10 visibility toggles per minute
            'get_user_profile': 60,  # 60 profile requests per minute
            'list_whistles': 60      # 60 whistle list requests per minute
        }
        
        # Default rate limit for unlisted tools
        self.default_rate_limit = 100
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Apply rate limiting to tool calls"""
        
        tool_name = context.message.name
        rate_key = self._get_rate_limit_key(context)
        
        if self._is_rate_limited(tool_name, rate_key):
            logger.warning(
                "Rate limit exceeded",
                tool_name=tool_name,
                rate_key=rate_key[:20] + "..." if len(rate_key) > 20 else rate_key
            )
            raise McpError(
                ErrorData(
                    code=-32000,
                    message=f"Rate limit exceeded for {tool_name}. Please try again later."
                )
            )
        
        # Record this request
        self._record_request(rate_key)
        
        return await call_next(context)
    
    def _get_rate_limit_key(self, context: MiddlewareContext) -> str:
        """Generate rate limiting key based on tool and context"""
        
        tool_name = context.message.name
        arguments = getattr(context.message, 'arguments', {})
        
        # For auth operations, use phone number if available
        if tool_name in ['sign_in', 'verify_otp', 'resend_otp']:
            phone = arguments.get('phone', 'unknown')
            country_code = arguments.get('country_code', '')
            return f"{tool_name}:{country_code}{phone}"
        
        # For protected operations, use access token hash
        access_token = arguments.get('access_token')
        if access_token:
            # Use last 8 characters as identifier
            token_id = access_token[-8:] if len(access_token) > 8 else access_token
            return f"{tool_name}:{token_id}"
        
        # Fallback to tool name only (less precise but still protective)
        return f"{tool_name}:anonymous"
    
    def _is_rate_limited(self, tool_name: str, rate_key: str) -> bool:
        """Check if the request should be rate limited"""
        
        rate_limit = self.rate_limits.get(tool_name, self.default_rate_limit)
        current_time = time.time()
        
        # Clean old requests (older than 1 minute)
        self.request_counts[rate_key] = [
            req_time for req_time in self.request_counts[rate_key]
            if current_time - req_time < 60
        ]
        
        # Check if rate limit exceeded
        return len(self.request_counts[rate_key]) >= rate_limit
    
    def _record_request(self, rate_key: str) -> None:
        """Record the current request timestamp"""
        self.request_counts[rate_key].append(time.time())
