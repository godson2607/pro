# models/user_model.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any

class Parent(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore unknowns

class Reachability(Parent):
    call: bool = Field(default=False)
    SMS: bool = Field(default=False)
    email: bool = Field(default=False)

class Quarantine(Parent):
    homeLocation: Optional[List[float]] = None
    activeAlert: bool = False

class UserProfile(Parent):
    id: str = Field(..., description="Unique user identifier", alias="_id")
    name: str
    phone: str
    countryCode: str
    active: bool = True
    verified: bool = False
    certified: bool = False
    visible: bool = True
    taxiProvider: bool = False
    usertype: Optional[str] = "individual"
    quarantineAdmin: Optional[bool] = False
    migrated: Optional[bool] = False
    safetyAlertsEnabled: Optional[bool] = False

    # Nested objects
    reachability: Optional[Reachability] = None
    quarantine: Optional[Quarantine] = None

    # Metadata
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None

    # Aliases for consistency
    id: str = Field(..., alias="_id")  # normalize _id → id

class UserProfileResponse(Parent):
    success: bool = True
    data: Optional[UserProfile] = None
