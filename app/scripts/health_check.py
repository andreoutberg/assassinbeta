#!/usr/bin/env python3
"""
Health check endpoint for the High-WR Trading System backend.
This script is used by Docker to verify the container is healthy.
"""

import sys
import os
import httpx
import asyncio
from typing import Dict, Any


async def check_health(host: str = "localhost", port: int = 8000) -> Dict[str, Any]:
    """
    Check the health of the backend service.

    Returns:
        Dict containing health status and details
    """
    url = f"http://{host}:{port}/api/health"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)

            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "code": response.status_code,
                    "data": response.json() if response.content else {}
                }
            else:
                return {
                    "status": "unhealthy",
                    "code": response.status_code,
                    "error": f"HTTP {response.status_code}"
                }

    except httpx.ConnectError:
        return {
            "status": "unhealthy",
            "error": "Cannot connect to service"
        }
    except httpx.TimeoutException:
        return {
            "status": "unhealthy",
            "error": "Request timeout"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


async def main():
    """Main health check function."""
    # Get host and port from environment variables
    host = os.getenv("HEALTH_CHECK_HOST", "localhost")
    port = int(os.getenv("HEALTH_CHECK_PORT", "8000"))

    # Perform health check
    result = await check_health(host, port)

    if result["status"] == "healthy":
        print(f"✓ Service is healthy")
        sys.exit(0)
    else:
        print(f"✗ Service is unhealthy: {result.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())