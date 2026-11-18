"""Настройки приложения. Читаются из переменных окружения и файла .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    keitaro_url: str = ""
    keitaro_api_key: str = ""
    keitaro_timeout_seconds: float = 20.0
    # Сколько секунд держим в памяти справочники Keitaro (офферы, домены и т.д.)
    keitaro_cache_seconds: float = 60.0

    # Домен, группа и источник новой кампании — по имени, id ищем через API
    keitaro_domain: str = ""
    keitaro_group: str = ""
    keitaro_source: str = ""

    campaign_prefix: str = ""
    # Куда первый поток отправляет посетителей из выбранных стран
    geo_redirect_url: str = "https://google.com"

    database_url: str = "sqlite:///./adrobot.db"

    # С каких адресов можно открывать приложение (через запятую). Защита от DNS rebinding.
    allowed_hosts: str = "localhost,127.0.0.1"

    @property
    def domain_host(self) -> str:
        """Домен без схемы и слэшей: https://Tracker.Example.com/ -> tracker.example.com."""
        host = self.keitaro_domain.strip().lower()
        for scheme in ("https://", "http://"):
            host = host.removeprefix(scheme)
        return host.strip("/")

    @property
    def allowed_host_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @property
    def keitaro_base_url(self) -> str:
        return self.keitaro_url.strip().rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
