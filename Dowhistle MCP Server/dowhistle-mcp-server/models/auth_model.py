from pydantic import BaseModel, Field, ConfigDict, computed_field
from typing import Optional, List


# -------------------------
# Shared Parent (ignore unknown fields)
# -------------------------
class Parent(BaseModel):
    model_config = ConfigDict(extra="ignore")


# -------------------------
# Sign In
# -------------------------
class SignInRequest(Parent):
    phone: str = Field(..., description="Digits only, without country code")
    countryCode: str = Field(..., alias="countryCode", description="Country code starting with +")
    name: str
    latitude: float = Field(..., ge=-90, le=90, description="Latitude coordinate (-90 to 90)")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude coordinate (-180 to 180)")

    @computed_field(alias="location", return_type=List[float])
    @property
    def location_array(self) -> List[float]:
        return [self.latitude, self.longitude]


class SignInUser(Parent):
    id: str = Field(..., description="Unique user identifier")
    mongo_id: Optional[str] = Field(None, alias="_id", description="MongoDB ObjectId (alternative user identifier)")
    otp: str = Field(..., description="One-time password for verification")


class SignInResponse(Parent):
    message: str
    user: SignInUser
    success: bool = Field(..., description="Indicates whether sign in was successful")


class SignInErrorResponse(Parent):
    success: bool = False
    error: str
    payload: Optional[SignInRequest] = None


# -------------------------
# Verify OTP
# -------------------------
class VerifyOtpRequest(Parent):
    id: str
    otp: str


class VerifyOtpUser(Parent):
    name: str
    phone: str
    countryCode: str = Field(..., alias="countryCode")
    taxiProvider: bool
    certified: bool


class VerifyOtpResponse(Parent):
    message: str
    user: VerifyOtpUser
    token: str
    uploadToken: str = Field(..., alias="uploadToken")
    success: bool = Field(..., description="Indicates whether OTP verification was successful")


class VerifyOtpErrorResponse(Parent):
    success: bool = False
    error: str
    payload: Optional[VerifyOtpRequest] = None


# -------------------------
# Resend OTP
# -------------------------
class ResendOtpRequest(Parent):
    userid: str = Field(..., alias="userid")


class ResendOtpResponse(Parent):
    message: str
    success: bool = Field(..., description="Indicates whether resend was successful")


class ResendOtpErrorResponse(Parent):
    success: bool = False
    error: str
    payload: Optional[ResendOtpRequest] = None
