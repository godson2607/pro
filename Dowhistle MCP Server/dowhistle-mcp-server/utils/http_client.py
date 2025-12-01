import httpx
import structlog
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import settings

logger = structlog.get_logger()


class APIClient:
    def __init__(self):
        self.base_url = settings.EXPRESS_API_BASE_URL
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "MCP-Server/1.0",
        }
        if settings.API_KEY:
            self.headers["Authorization"] = f"Bearer {settings.API_KEY}"

    def get_base_url_for_endpoint(self, endpoint: str) -> str:
        """Get appropriate base URL based on endpoint and environment"""
        # Check if we're in development mode and endpoint is search-related
        is_development = (
            settings.EXPRESS_API_BASE_URL == "https://dowhistle-dev.herokuapp.com/v3"
        )
        is_search_endpoint = endpoint.strip("/").startswith("searchAround")

        if is_development and is_search_endpoint:
            # Use production URL for search endpoints in development
            return "https://dowhistle.herokuapp.com/v3"
        else:
            # Use configured base URL for all other cases
            return self.base_url

    @retry(
        stop=stop_after_attempt(settings.MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request to Express API with retry logic"""

        request_headers = {**self.headers, **(headers or {})}
        base_url = self.get_base_url_for_endpoint(endpoint)
        url = f"{base_url}/{endpoint.lstrip('/')}"

        logger.info(
            "Making API request",
            method=method,
            url=url,
            base_url=base_url,
            has_data=data is not None,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    headers=request_headers,
                )
                response.raise_for_status()

                result = response.json()
                logger.info(
                    "API request successful",
                    status_code=response.status_code,
                    endpoint=endpoint,
                    base_url=base_url,
                )
                return result

            except httpx.HTTPStatusError as e:
                logger.error(
                    "API request failed",
                    status_code=e.response.status_code,
                    error=str(e),
                    endpoint=endpoint,
                    base_url=base_url,
                    response_text=e.response.text,
                )
                raise
            except Exception as e:
                logger.error(
                    "API request error",
                    error=str(e),
                    endpoint=endpoint,
                    base_url=base_url,
                )
                raise


# Global client instance
api_client = APIClient()
