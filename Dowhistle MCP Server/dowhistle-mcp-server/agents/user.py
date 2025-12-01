# agents/user.py
from fastmcp import FastMCP
from typing import Annotated, Literal
import structlog
from utils.http_client import api_client
from pydantic import Field
from models.user_model import UserProfileResponse, UserProfile

logger = structlog.get_logger()


class UserAgent:
    def __init__(self, mcp: FastMCP):
        self.mcp = mcp
        self.register_tools()
    
    def register_tools(self):
        @self.mcp.tool()
        async def toggle_visibility(
            access_token: Annotated[
                str, Field(description="User authentication token from sign_in or verify_otp")
            ],
            visible: Annotated[
                Literal["true", "false"],
                Field(description="Whether the user should be visible ('true') or hidden ('false')")
            ],
        ) -> UserProfileResponse:
            """
            Toggle user visibility status.

            This function updates the user's visibility setting on the backend.  
            If `visible` is `"true"`, the user becomes publicly visible.  
            If `visible` is `"false"`, the user is hidden.

            Args:
                access_token (str): User authentication token obtained from sign_in or verify_otp.
                visible (Literal["true", "false"]): Whether the user should be visible ("true") or hidden ("false").

            Returns:
                UserProfileResponse: Success flag and updated user profile data if successful.
            """
            try:
                # Convert to boolean for API call
                visible_bool = visible == "true"
                payload = {"visible": visible_bool}

                print("toggle_visibility payload:", payload)  # debug log

                result = await api_client.request(
                    method="PUT",
                    endpoint="/user",
                    data=payload,
                    headers={"Authorization": access_token}
                )

                logger.info("Visibility toggle successful", visible=visible)

                if "user" not in result:
                    return UserProfileResponse(success=False, data=None)  # type: ignore

                user_data = result["user"]
                validated_response = UserProfile.model_validate(user_data)

                return UserProfileResponse(success=True, data=validated_response)

            except Exception as e:
                logger.error(
                    "Visibility toggle failed",
                    error=str(e),
                    visible=visible
                )
                return UserProfileResponse(
                    success=False,
                    message="An unexpected error occurred while toggling visibility. Please try again later."
                )  # type: ignore

        @self.mcp.tool()
        async def get_user_profile(
            access_token: Annotated[
                str, Field(description="User authentication token from sign_in or verify_otp")
            ]
        ) -> UserProfileResponse:
            """
            Retrieve the user profile details.

            This function fetches the user's profile information from the backend,  
            including whistles and visibility status.

            Args:
                access_token (str): User authentication token obtained from sign_in or verify_otp.

            Returns:
                UserProfileResponse: Success flag and user profile data if retrieval succeeds.
            """
            try:
                result = await api_client.request(
                    method="GET",
                    endpoint="/user",
                    headers={"Authorization": access_token}
                )

                if "user" not in result:
                    return UserProfileResponse(success=False, data=None)  # type: ignore

                user_data = result["user"]
                validated_response = UserProfile.model_validate(user_data)

                # debug log
                print(f"get_user_profile response: {validated_response}")

                logger.info(
                    "User profile retrieved successfully",
                    user_id=validated_response.id
                )

                return UserProfileResponse(success=True, data=validated_response)

            except Exception as e:
                logger.error("User profile retrieval failed", error=str(e))
                return UserProfileResponse(
                    success=False,
                    message="An unexpected error occurred while retrieving the profile. Please try again later."
                )  # type: ignore
