from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
# Authentication dependencies are handled in auth_utils.py

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from app.database import init_db
from app.routers import auth, wallet, keys, payments


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize database
    await init_db()
    yield
    # Shutdown: cleanup if needed

app = FastAPI(
    title="HNG Paystack Wallet API",
    description="A Backend Wallet Service with JWT Authentication and Paystack Integration",
    version="1.0.0",
    # lifespan=lifespan, # Disabled for testing
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
app.include_router(wallet.router)
app.include_router(keys.router)
app.include_router(payments.router)


@app.get("/")
async def root():
    return {
        "message": "HNG Paystack Wallet API",
        "endpoints": {
            "docs": "/docs",
            "google_auth": "/auth/google",
            "wallet_deposit": "/wallet/deposit",
            "wallet_info": "/wallet/info",
            "wallet_balance": "/wallet/balance"
        }
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
