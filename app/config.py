from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[1] / ".env", extra="ignore", hide_input_in_errors=True)
    environment: Literal["development", "test", "production"] = "development"
    registration_enabled: bool | None = None
    ai_global_hourly_limit: int = Field(default=100, ge=1, le=10000)
    database_url: str
    jwt_secret: str = Field(min_length=32)
    jwt_issuer: str = "expenses-diary"
    jwt_audience: str = "expenses-diary-mobile"
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    cors_origins: list[str] = ["http://localhost:8081"]
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    @model_validator(mode="after")
    def production(self):
        if self.registration_enabled is None:
            self.registration_enabled = self.environment != "production"
        if self.environment == "production":
            if self.jwt_secret.upper().startswith(("REPLACE_", "CHANGE_", "TESTING-", "CI-")) or len(set(self.jwt_secret)) < 12:
                raise ValueError("Generate a random JWT secret for production")
            if not self.database_url.startswith("mysql+pymysql://"):
                raise ValueError("Production requires MySQL")
            if not all([self.smtp_host, self.smtp_from, self.smtp_user, self.smtp_password]):
                raise ValueError("Production requires SMTP configuration")
            if not self.allowed_hosts or any(
                not host or any(c in host for c in "*/:@ ")
                or host in {"localhost", "127.0.0.1", "testserver"}
                for host in self.allowed_hosts
            ) or any(
                urlsplit(origin).scheme != "https" or not urlsplit(origin).hostname
                or urlsplit(origin).username is not None or urlsplit(origin).password is not None
                or urlsplit(origin).path or urlsplit(origin).query or urlsplit(origin).fragment
                or "*" in origin
                for origin in self.cors_origins
            ):
                raise ValueError("Production requires explicit hosts and HTTPS origins")
        return self


settings = Settings()
