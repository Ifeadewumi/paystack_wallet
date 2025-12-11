#!/usr/bin/env python3
"""
Deployment script that runs database migrations before starting the app.
"""
import subprocess
import sys
import os

def run_migrations():
    """Run Alembic migrations."""
    try:
        print("Running database migrations...")
        result = subprocess.run(["alembic", "upgrade", "head"], 
                              capture_output=True, text=True, check=True)
        print("Migrations completed successfully!")
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Migration failed: {e}")
        print(f"Error output: {e.stderr}")
        return False
    except FileNotFoundError:
        print("Alembic not found. Make sure it's installed.")
        return False

if __name__ == "__main__":
    # Run migrations
    if not run_migrations():
        print("Deployment failed due to migration errors.")
        sys.exit(1)
    
    print("Deployment completed successfully!")