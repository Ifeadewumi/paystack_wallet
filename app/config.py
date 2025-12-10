from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Core Application
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    api_key_prefix: str = "sk_live"

    # Database
    database_url: str
    
    # Google OAuth
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    
    # Paystack
    paystack_secret_key: str
    paystack_webhook_secret: str
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
