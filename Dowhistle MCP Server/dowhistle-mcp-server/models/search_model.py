from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class SearchNearMeRequest(BaseModel):
    latitude: float
    longitude: float
    radius: Optional[float] = 10.0  # Default radius of 2km
    keyword: Optional[str] = None
    # category: Optional[str] = None
    limit: Optional[int] = 100


class Provider(BaseModel):
    id: str
    name: str
    phone: str
    address: str
    distance: float
    latitude: float
    longitude: float
    # category: Optional[str] = None
    rating: Optional[float] = None


class SearchNearMeResponse(BaseModel):
    providers: List[Provider]
    total_count: int
    search_radius: float
    search_location: Dict[str, float]
