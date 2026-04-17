from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    tracker_oauth_token: str
    tracker_org_id: str
    tracker_api_base: str = "https://api.tracker.yandex.net"
    tracker_web_base: str = "https://tracker.yandex.ru"
    # "360" for Yandex 360 orgs (X-Org-ID header) or "cloud" for Yandex Cloud orgs (X-Cloud-Org-ID).
    tracker_org_type: str = "360"

    portfolio_domain_id: str
    portfolio_subdomain_id: str
    portfolio_team_id: str

    pachca_access_token: str
    pachca_api_base: str = "https://api.pachca.com/api/shared/v1"
    pachca_target_chat_id: int

    webhook_api_key: str

    app_host: str = "0.0.0.0"
    app_port: int = 8080
    log_level: str = "INFO"

    status_freshness_days: int = 6
    weekly_status_tag: str = "#WeeklyStatus"


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
