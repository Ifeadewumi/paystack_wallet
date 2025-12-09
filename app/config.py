from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str
    
    # Google OAuth
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    
    # Paystack
    paystack_secret_key: str
    paystack_webhook_secret: str
    
    # Application
    app_secret_key: str
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
