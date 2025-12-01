import os
from typing import Optional, Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Environment Configuration
    ENVIRONMENT: Literal["development", "staging", "production"] = Field(
        default="development"
    )

    # Transport Configuration (Only HTTP transport)
    TRANSPORT_MODE: Optional[Literal["http"]] = Field(
        default="http",  # Force the transport mode to be HTTP
    )

    # API Configuration
    EXPRESS_API_BASE_URL: str = Field(default="https://dowhistle.herokuapp.com/v3")
    
    # New field for PORT (from environment)
    PORT: Optional[int] = Field(default=None)

    # Authentication
    API_KEY: Optional[str] = Field(default=None)
    OPENAI_API_KEY: str = Field()
    # Logging
    LOG_LEVEL: str = Field(default="INFO")

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = Field(default=60)

    # Retry Configuration
    MAX_RETRIES: int = Field(default=3)
    RETRY_DELAY: float = Field(default=1.0)

    # Connection Configuration
    CONNECTION_TIMEOUT: int = Field(default=30)
    REQUEST_TIMEOUT: int = Field(default=30)

    # CORS Configuration (for HTTP transport)
    CORS_ORIGINS: str = Field(default="*")
    CORS_METHODS: str = Field(default="GET,POST,OPTIONS")
    CORS_HEADERS: str = Field(default="Content-Type,Authorization")

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def set_log_level(cls, v, info):
        """Auto-adjust log level based on environment if not explicitly set"""
        if v != "INFO":  # If explicitly set, keep it
            return v.upper()

        # Get environment from the data being validated
        environment = info.data.get("ENVIRONMENT", "development")
        if environment == "production":
            return "INFO"
        elif environment == "staging":
            return "DEBUG"
        else:
            return "DEBUG"

    @field_validator("PORT", mode="before")
    @classmethod
    def handle_render_port(cls, v, info):
        """Handle Render.com PORT environment variable"""
        render_port = os.getenv("PORT")
        if render_port:
            return int(render_port)
        return v

    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.ENVIRONMENT == "production"

    @property
    def server_info(self) -> dict:
        """Get server configuration info"""
        return {
            "environment": self.ENVIRONMENT,
            "transport_mode": self.TRANSPORT_MODE,
            "mcp_port": self.PORT,
            "api_base_url": self.EXPRESS_API_BASE_URL,
            "log_level": self.LOG_LEVEL,
        }

    def model_post_init(self, __context) -> None:
        """Post-initialization validation and logging"""
        print("🚀 Server Configuration:")
        print(f"   Environment: {self.ENVIRONMENT}")
        print(f"   Transport: {self.TRANSPORT_MODE}")
        print(f"   MCP Port: {self.PORT}")
        print(f"   API Base URL: {self.EXPRESS_API_BASE_URL}")
        print(f"   Log Level: {self.LOG_LEVEL}")


settings = Settings()
