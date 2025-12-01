from fastmcp import FastMCP
from typing import Optional, Dict, Any, Annotated
import structlog
from utils.http_client import api_client
from models.search_model import Provider, SearchNearMeResponse
from utils.helper import compute_feedback_rating
from pydantic import Field

logger = structlog.get_logger()


class SearchAgent:
    def __init__(self, mcp: FastMCP):
        self.mcp = mcp
        self.register_tools()

    def register_tools(self):
        @self.mcp.tool()
        async def search_businesses(
            latitude: Annotated[
                float, Field(description="Latitude of the search location")
            ],
            longitude: Annotated[
                float, Field(description="Longitude of the search location")
            ],
            radius: Annotated[
                int,
                Field(
                    description="Search radius in kilometers", ge=1, le=1000, default=10
                ),
            ],
            keyword: Annotated[
                str,
                Field(
                    description="Keyword to search for (e.g., 'mechanic', 'restaurant')",
                    default="",
                ),
            ],
            limit: Annotated[
                int,
                Field(
                    description="Maximum number of results to return",
                    ge=1,
                    le=1000,
                    default=10,
                ),
            ],
        ) -> SearchNearMeResponse:
            """
            Search for providers near a specific location.

            Args:
                latitude: The latitude coordinate of the search location
                longitude: The longitude coordinate of the search location
                radius: Search radius in kilometers (default: 10)
                keyword: Keyword to search for (e.g., "mechanic", "restaurant")
                limit: Maximum number of results to return (default: 10)

            Returns:
                A dictionary containing providers found near the location
            """
            try:
                # Ensure the keyword is a single value
                keyword = self._sanitize_keyword(keyword)
                print("keyword", keyword)

                payload = {
                    "keyword": keyword
                    or "",  # Default to empty string if keyword is empty
                    "limit": limit,
                    "location": [longitude, latitude],
                    "provider": True,
                    "radius": radius,
                    "visible": True,
                }

                result = await api_client.request(
                    method="POST",
                    endpoint="/searchAround",
                    data=payload,
                )

                logger.info(
                    "Search completed",
                    query=keyword,
                    results_count=len(result.get("results", [])),
                )

                providers = self._normalize_providers(result)
                print("providers", providers)

                response = SearchNearMeResponse(
                    providers=providers,
                    total_count=len(providers),
                    search_radius=radius,
                    search_location={
                        "latitude": latitude,
                        "longitude": longitude,
                    },
                )

                # ✅ Always return JSON-safe dict
                return response.model_dump()

            except Exception as e:
                logger.error("Search failed", error=str(e))

                error_response = SearchNearMeResponse(
                    providers=[],
                    total_count=0,
                    search_radius=radius,
                    search_location={
                        "latitude": latitude,
                        "longitude": longitude,
                    },
                )

                # ✅ Include error info in JSON response
                resp = error_response.model_dump()
                resp["error"] = f"Unexpected error: {str(e)}"
                return resp

    def _normalize_providers(self, result):
        providers = []
        data = result
        providers_data = self._extract_providers_data(data)
        for provider_data in providers_data:
            if "item" in provider_data:  # matchingWhistles format
                provider = self._normalize_matching_whistle(provider_data["item"])
            else:  # direct provider format
                provider = self._normalize_direct_provider(provider_data)
            providers.append(provider)
        return providers

    def _extract_providers_data(self, data):
        if isinstance(data, dict):
            providers_data = data.get("providers", [])
            if not providers_data and "matchingWhistles" in data:
                providers_data = data.get("matchingWhistles", [])
        elif isinstance(data, list):
            providers_data = data
        else:
            providers_data = []
        return providers_data

    def _normalize_matching_whistle(self, item):
        return Provider(
            id=item.get("_id", ""),
            name=item.get("name", ""),
            phone=f"{item.get('countryCode', '')} {item.get('phone', '')}",
            address=item.get("location", {}).get("address", ""),
            distance=round(item.get("dis", 0.0), 1),
            latitude=(
                item.get("location", {}).get("coordinates", [0, 0])[1]
                if item.get("location", {}).get("coordinates")
                else 0.0
            ),
            longitude=(
                item.get("location", {}).get("coordinates", [0, 0])[0]
                if item.get("location", {}).get("coordinates")
                else 0.0
            ),
            rating=compute_feedback_rating(item),
        )

    def _normalize_direct_provider(self, provider_data):
        return Provider(
            id=provider_data.get("id", str(provider_data.get("_id", ""))),
            name=provider_data.get("name", provider_data.get("title", "")),
            phone=f"{provider_data.get('countryCode', '')} {provider_data.get('phone', '')}",
            address=provider_data.get("address", provider_data.get("location", "")),
            distance=round(provider_data.get("distance", 0.0), 1),
            latitude=provider_data.get("latitude", provider_data.get("lat", 0.0)),
            longitude=provider_data.get("longitude", provider_data.get("lng", 0.0)),
            rating=compute_feedback_rating(provider_data),
        )

    def _sanitize_keyword(self, keyword: str) -> str:
        """Sanitize and ensure the keyword is a single value"""
        if "|" in keyword:
            logger.warning(
                "Multiple keywords detected, only the first one will be used."
            )
            # Split and take the first value, ensuring it's a single clean value
            keyword = keyword.split("|")[0].strip()
        return keyword
