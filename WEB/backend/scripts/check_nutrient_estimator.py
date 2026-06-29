"""Quick test for the nutrient estimation endpoint."""
import asyncio
import json
import httpx

BASE = "http://localhost:8005/api/v1"


async def main():
    async with httpx.AsyncClient() as c:
        # Get CSRF
        r = await c.get(f"{BASE}/auth/csrf-cookie")
        csrf = r.cookies.get("csrf_token")
        print(f"CSRF: {csrf[:20]}...")

        # Login
        r = await c.post(
            f"{BASE}/auth/login",
            data={"username": "developer@hntsolutions.com", "password": "TestPass123!"},
            headers={"X-CSRF-Token": csrf},
        )
        resp = r.json()
        if "access_token" not in resp:
            print(f"Login failed: {resp}")
            return
        token = resp["access_token"]
        print("Logged in OK")

        headers = {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf}

        # Test 1: USDA-searchable food
        print("\n--- Test 1: grilled chicken breast (should hit USDA) ---")
        r = await c.post(
            f"{BASE}/nutrition/estimate-nutrients",
            json={"food_name": "grilled chicken breast", "serving_size": "170g"},
            headers=headers,
        )
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Source: {data.get('source')}, Confidence: {data.get('confidence')}")
        nutrients = data.get("nutrients", {})
        print(f"Calories: {nutrients.get('calories')}, Protein: {nutrients.get('protein_g')}g")
        print(f"Cached: {data.get('cached')}")

        # Test 2: Same food again (should hit cache)
        print("\n--- Test 2: grilled chicken breast again (should hit cache) ---")
        r = await c.post(
            f"{BASE}/nutrition/estimate-nutrients",
            json={"food_name": "grilled chicken breast"},
            headers=headers,
        )
        data = r.json()
        print(f"Source: {data.get('source')}, Cached: {data.get('cached')}")

        # Test 3: Regional food unlikely in USDA
        print("\n--- Test 3: jollof rice (may need AI fallback) ---")
        r = await c.post(
            f"{BASE}/nutrition/estimate-nutrients",
            json={"food_name": "jollof rice", "serving_size": "1 cup"},
            headers=headers,
        )
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Source: {data.get('source')}, Confidence: {data.get('confidence')}")
        nutrients = data.get("nutrients", {})
        print(f"Calories: {nutrients.get('calories')}, Protein: {nutrients.get('protein_g')}g")
        print(f"Cached: {data.get('cached')}, AI Model: {data.get('ai_model')}")


asyncio.run(main())
