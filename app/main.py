from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
# Removed: from fastapi.security import OAuth2PasswordBearer
from app.dependencies import oauth2_scheme # Added this import

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from app.database import init_db
from app.routers import auth, payments


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize database
    await init_db()
    yield
    # Shutdown: cleanup if needed


app = FastAPI(
    title="HNG Stage 8 - Google OAuth & Paystack Integration",
    description="Backend API for Google Sign-In and Paystack Payment",
    version="1.0.0",
    lifespan=lifespan,
    openapi_extra={
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "Enter your JWT token in the format 'Bearer <token>'"
                }
            }
        }
    }
)

# CORS middleware (configure as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(payments.router)


@app.get("/")
async def root():
    return {
        "message": "HNG Stage 8 API",
        "endpoints": {
            "docs": "/docs",
            "google_auth": "/auth/google",
            "payment_initiate": "/payments/paystack/initiate"
        }
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
