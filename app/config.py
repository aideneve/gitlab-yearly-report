import logging
import sys

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False)

    gitlab_url: str
    gitlab_token: str
    port: int = 8080
    request_timeout: int = 30


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        logger.error("Invalid configuration, check GITLAB_URL and GITLAB_TOKEN: %s", exc)
        sys.exit(1)
