from fastmcp import FastMCP
from typing import Union
import re
import structlog
from pydantic import BaseModel
from utils.http_client import api_client
from models.auth_model import (
    SignInRequest,
    SignInResponse,
    SignInUser,
    VerifyOtpRequest,
    VerifyOtpResponse,
    VerifyOtpUser,
    ResendOtpRequest,
    ResendOtpResponse,
    ResendOtpErrorResponse,
    VerifyOtpErrorResponse,
    SignInErrorResponse,
)


logger = structlog.get_logger()


class AuthAgent:
    def __init__(self, mcp: FastMCP):
        self.mcp = mcp
        self.register_tools()

    def register_tools(self):
        # -------------------------
        # Sign In Tool
        # -------------------------
        @self.mcp.tool()
        async def sign_in(
            phone: str,
            country_code: str,
            name: str,
            latitude: float,
            longitude: float,
        ) -> Union[SignInResponse, SignInErrorResponse]:
            """
            Authenticate user with phone, country code, name, latitude and longitude using OTP verification.

            Args:
                phone: Digits only, without country code (e.g., "9994076214")
                country_code: User's country calling code (supported values: "+1" for USA, "+91" for India, or just "1", "91")
                name: User name
                latitude: Latitude coordinate (-90 to 90)
                longitude: Longitude coordinate (-180 to 180)

            Returns:
                SignInResponse: Contains message and user details
                SignInErrorResponse: Contains error message and request payload
            """
            sign_in_request = None
            try:
                # Validate coordinates
                lat = float(latitude)
                lon = float(longitude)
                if not (-90.0 <= lat <= 90.0):
                    raise ValueError("latitude must be between -90 and 90.")
                if not (-180.0 <= lon <= 180.0):
                    raise ValueError("longitude must be between -180 and 180.")

                # Process phone number
                raw_phone = phone.strip()
                raw_phone = re.sub(r"[()\-\s]", "", raw_phone)

                # Case: starts with +<countrycode><number>
                if raw_phone.startswith("+"):
                    match = re.match(r"^(\+\d{1,3})(\d+)$", raw_phone)
                    if not match:
                        raise ValueError(
                            "Invalid phone format. Expected '+<code><number>'."
                        )
                    country_code = match.group(1)
                    raw_phone = match.group(2)

                # Case: starts with 0 (strip leading zeros)
                elif raw_phone.startswith("0"):
                    raw_phone = raw_phone.lstrip("0")

                # Ensure phone digits only
                if not raw_phone.isdigit():
                    raise ValueError(
                        "Phone must contain digits only, without country code."
                    )

                # Fix country code formatting - ensure it starts with '+'
                country_code = country_code.strip()
                if not country_code.startswith("+"):
                    if country_code.isdigit():
                        country_code = "+" + country_code
                    else:
                        raise ValueError(
                            "Country code must be digits or start with '+' followed by digits."
                        )

                # Validate country_code format
                if not country_code.startswith("+") or not country_code[1:].isdigit():
                    raise ValueError(
                        "Country code must start with '+' followed by digits."
                    )

                phone = raw_phone

                # Create request payload using Pydantic model for validation
                sign_in_request = SignInRequest(
                    phone=phone,
                    countryCode=country_code,
                    name=name,
                    latitude=latitude,
                    longitude=longitude,
                )

                # Convert to dict for API call
                payload = sign_in_request.model_dump(
                    by_alias=True, exclude={"latitude", "longitude"}
                )

                logger.debug("sign_in payload built", payload=payload)
                print("payload", payload)  # debug log

                # Make API request
                result = await api_client.request(
                    method="POST", endpoint="/twilio/sign-in", data=payload
                )

                # Validate response structure and create proper response model
                try:
                    validated_response = SignInResponse.model_validate(result)
                    logger.info(
                        "Sign in successful",
                        phone=phone,
                        country_code=country_code,
                        user_id=validated_response.user.mongo_id or validated_response.user.id,
                    )

                    return SignInResponse(
                        message=validated_response.message,
                        user=validated_response.user,
                        success=validated_response.success,
                    )

                except Exception as validation_error:
                    logger.warning(
                        "Response validation failed but attempting to create response",
                        error=str(validation_error),
                        response=result,
                    )

                    # Fallback: try to construct response from raw result
                    user_data = result.get("user", {})
                    return SignInResponse(
                        message=result.get("message", "Sign in successful"),
                        user=SignInUser(
                            id=user_data.get("id", ""),
                            _id=user_data.get("_id"),
                            otp=user_data.get("otp"),
                        ),
                        success=result.get("success", True),
                    )

            except Exception as e:
                logger.error("Sign in failed", error=str(e), phone=phone)
                return SignInErrorResponse(
                    error=str(e),
                    payload=sign_in_request,  # This will be None if validation failed before creation
                )

        # -------------------------
        # Verify OTP Tool
        # -------------------------
        @self.mcp.tool()
        async def verify_otp(
            otp_code: str, user_id: str,
        ) -> Union[VerifyOtpResponse, VerifyOtpErrorResponse]:
            """
            Verify OTP code for user authentication.

            Args:
                user_id: User ID returned from sign_in (must not be a phone number)
                otp_code: OTP code digits (6-digit string)

            Returns:
                VerifyOtpResponse: Contains message, user details, auth token, and upload token
                VerifyOtpErrorResponse: Contains error message and request payload
            """
            verify_otp_request = None
            try:
                if not user_id or not isinstance(user_id, str):
                    raise ValueError("Invalid user_id. Must be a non-empty string.")

                # Block mistake: passing phone number instead of user_id
                if user_id.isdigit() or user_id.startswith("+"):
                    raise ValueError(
                        "user_id looks like a phone number. Please provide valid user_id from sign_in."
                    )

                if not otp_code.isdigit():
                    raise ValueError("otp_code must contain only digits.")

                # Create request payload using Pydantic model for validation
                verify_otp_request = VerifyOtpRequest(id=user_id, otp=otp_code)

                # Convert to dict for API call
                payload = verify_otp_request.model_dump()

                print(" verify_otp payload", payload)  # debug log

                # Make API request
                result = await api_client.request(
                    method="POST", endpoint="/twilio/verify-otp", data=payload
                )

                # Validate response structure and create proper response model
                try:
                    validated_response = VerifyOtpResponse.model_validate(result)

                    logger.info(
                        "OTP verification successful",
                        user_id=user_id,
                        user_name=validated_response.user.name,
                    )

                    return validated_response

                except Exception as validation_error:
                    logger.warning(
                        "Response validation failed but attempting to create response",
                        error=str(validation_error),
                        response=result,
                    )

                    # Fallback: try to construct response from raw result
                    user_data = result.get("user", {})
                    return VerifyOtpResponse(
                        message=result.get("message", "OTP verified successfully"),
                        user=VerifyOtpUser(
                            name=user_data.get("name", ""),
                            phone=user_data.get("phone", ""),
                            countryCode=user_data.get("countryCode", ""),
                            taxiProvider=user_data.get("taxiProvider", False),
                            certified=user_data.get("certified", False),
                        ),
                        token=result.get("token", ""),
                        uploadToken=result.get("uploadToken", ""),
                    )

            except Exception as e:
                logger.error("OTP verification failed", error=str(e), user_id=user_id)
                return VerifyOtpErrorResponse(error=str(e), payload=verify_otp_request)

        # -------------------------
        # Resend OTP Tool
        # -------------------------
        @self.mcp.tool()
        async def resend_otp(
            user_id: str,
        ) -> Union[ResendOtpResponse, ResendOtpErrorResponse]:
            """
            Resend OTP code to user phone number.

            Args:
                user_id: User ID returned from sign_in (must not be a phone number)

            Returns:
                ResendOtpResponse: Contains success message
                ResendOtpErrorResponse: Contains error message and request payload
            """
            resend_otp_request = None
            try:
                if not user_id or not isinstance(user_id, str):
                    raise ValueError("Invalid user_id. Must be a non-empty string.")

                # Block mistake: passing phone number
                if user_id.isdigit() or user_id.startswith("+"):
                    raise ValueError(
                        "user_id looks like a phone number. Please provide valid user_id from sign_in."
                    )

                # Create request payload using Pydantic model for validation
                resend_otp_request = ResendOtpRequest(userid=user_id)

                # Convert to dict for API call
                payload = resend_otp_request.model_dump()

                # Make API request
                result = await api_client.request(
                    method="POST", endpoint="/twilio/resend-otp", data=payload
                )

                # Validate response structure and create proper response model
                try:
                    validated_response = ResendOtpResponse.model_validate(result)
                    logger.info(
                        "OTP resent successfully",
                        user_id=user_id,
                        message=validated_response.message,
                    )

                    return validated_response

                except Exception as validation_error:
                    logger.warning(
                        "Response validation failed but attempting to create response",
                        error=str(validation_error),
                        response=result,
                    )

                    # Fallback: try to construct response from raw result
                    return ResendOtpResponse(
                        message=result.get("message", "OTP sent successfully")
                    )

            except Exception as e:
                logger.error("OTP resend failed", error=str(e), user_id=user_id)
                return ResendOtpErrorResponse(error=str(e), payload=resend_otp_request)
