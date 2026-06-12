import aiohttp
import asyncio
import dns.resolver
import pickle
import os
import re
import requests
import uuid
import whois
import json
import numpy as np
import unicodedata

import psycopg
import asyncio
from psycopg.rows import dict_row
from psycopg.types.json import Json

from datetime import datetime
from urllib.parse import urlparse
from typing import Dict, Any, Tuple, List, Optional
from dotenv import load_dotenv
from disposable_email_domains import blocklist as DISPOSABLE_DOMAINS

TRUELIST_API_KEY = os.getenv("TRUELIST_API_KEY", "eyJhbGciOiJIUzI1NiJ9.eyJpZCI6ImQ2OTJiZDQ1LTExMDItNDYxNi1iYzFjLWZhNmNlYzI3NTUwNSIsImV4cGlyZXNfYXQiOm51bGx9.rN29HHXJhdWTMeQM3TMtGz-aPcaE0TD__rEWstrvUxM")
API_SEMAPHORE = asyncio.Semaphore(10)
HTTP_PROXY_URL = os.environ.get('HTTP_PROXY')
HTTPS_PROXY_URL = os.environ.get('HTTPS_PROXY', HTTP_PROXY_URL)

# Global proxy configuration for all HTTP requests
PROXY_CONFIG = None
if HTTP_PROXY_URL:
    PROXY_CONFIG = {
        'http': HTTP_PROXY_URL,
        'https': HTTPS_PROXY_URL or HTTP_PROXY_URL
    }
    print(f"🌐 Proxy enabled: {HTTP_PROXY_URL[:50]}... (all API requests will use this IP)")

class EmailVerificationUnavailableError(Exception):
    """Raised when email verification API is unavailable (no credits, bad key, network error, etc.)"""
    pass

class LRUCache:
    """LRU Cache implementation with TTL support"""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache: Dict[str, Any] = {}
        self.timestamps: Dict[str, datetime] = {}
        self.access_order: list = []

    def __contains__(self, key: str) -> bool:
        if key in self.cache:
            # Update access order
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
            return True
        return False

    def __getitem__(self, key: str) -> Any:
        if key in self.cache:
            # Update access order
            self.access_order.remove(key)
            self.access_order.append(key)
            return self.cache[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any):
        if key in self.cache:
            # Update existing
            self.access_order.remove(key)
        elif len(self.cache) >= self.max_size:
            # Remove least recently used
            lru_key = self.access_order.pop(0)
            del self.cache[lru_key]
            del self.timestamps[lru_key]

        # Add new item
        self.cache[key] = value
        self.timestamps[key] = datetime.now()
        self.access_order.append(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def is_expired(self, key: str, ttl_hours: int) -> bool:
        if key not in self.timestamps:
            return True
        age = datetime.now() - self.timestamps[key]
        return age.total_seconds() > (ttl_hours * 3600)

    def cleanup_expired(self, ttl_hours: int):
        """Remove expired items from cache"""
        expired_keys = [key for key in list(self.cache.keys()) if self.is_expired(key, ttl_hours)]
        for key in expired_keys:
            del self.cache[key]
            del self.timestamps[key]
            if key in self.access_order:
                self.access_order.remove(key)

validation_cache = LRUCache(max_size=1000)
async def check_truelist_email(lead: dict) -> Tuple[bool, dict]:
    """
    Check email validity using TrueList API (fallback when MEV not configured).
    
    TrueList API: https://apidocs.truelist.io/#tag/Single-email-validation
    Only accepts "email_ok" status (equivalent to MEV "Valid").
    
    Retry logic: Up to 3 attempts with 10s wait between retries.
    """
    email = lead['email']
    if not email:
        return False, {
            "stage": "Stage 3: TrueList",
            "check_name": "check_truelist_email",
            "message": "No email provided",
            "failed_fields": ["email"]
        }

    # cache_key = f"truelist:{email}"
    # if cache_key in validation_cache and not validation_cache.is_expired(cache_key, CACHE_TTLS["myemailverifier"]):
    #     print(f"   💾 Using cached TrueList result for: {email}")
    #     return validation_cache[cache_key]

    # print(TRUELIST_API_KEY)
    # exit()

    max_retries = 2
    retry_delay = 3

    for attempt in range(1, max_retries + 1):
        try:
            async with API_SEMAPHORE:
                async with aiohttp.ClientSession() as session:
                    # TrueList single email validation endpoint
                    # API docs: https://apidocs.truelist.io/#tag/Single-email-validation
                    # NOTE: Uses query parameters, not JSON body
                    url = f"https://api.truelist.io/api/v1/verify_inline?email={email}"
                    headers = {"Authorization": f"Bearer {TRUELIST_API_KEY}"}
                    
                    if attempt == 1:
                        print(f"   📞 Calling TrueList API for: {email}")
                    else:
                        print(f"   🔄 Retry {attempt}/{max_retries} for: {email}")
                    
                    async with session.post(url, headers=headers, timeout=30, proxy=HTTP_PROXY_URL) as response:
                        if response.status in [401, 402, 403, 429, 500, 502, 503, 504]:
                            print(f"   🚨 TrueList API error (HTTP {response.status})")
                            # raise EmailVerificationUnavailableError(f"TrueList API unavailable (HTTP {response.status})")
                            return False, "pending"
                        
                        data = await response.json()
                        print(f"   📥 TrueList Response: {data}")
                        
                        # TrueList returns: {"emails": [{"email_sub_state": "email_ok", ...}]}
                        emails = data.get("emails", [])
                        if not emails:
                            # raise Exception("No email results in TrueList response")
                            return False, "No email results in TrueList response"
                        
                        email_data = emails[0]
                        status = email_data.get("email_sub_state", "unknown")
                        email_state = email_data.get("email_state", "unknown")
                        
                        # Store metadata in lead
                        lead["email_verifier_status"] = status
                        lead["email_verifier_disposable"] = status in ["disposable", "is_disposable"]
                        lead["email_verifier_catch_all"] = status == "accept_all"
                        lead["email_verifier_provider"] = "truelist"
                        
                        # Only accept "email_ok" (equivalent to MEV "Valid")
                        if status == "email_ok":
                            result = (True, {})
                        elif status == "accept_all":
                            result = (False, {
                                "stage": "Stage 3: TrueList",
                                "check_name": "check_truelist_email",
                                "message": "Email is catch-all/accept-all (instant rejection)",
                                "failed_fields": ["email"]
                            })
                        elif status in ["disposable", "is_disposable"]:
                            result = (False, {
                                "stage": "Stage 3: TrueList",
                                "check_name": "check_truelist_email",
                                "message": "Email is from a disposable provider",
                                "failed_fields": ["email"]
                            })
                        elif status == "is_role":
                            result = (False, {
                                "stage": "Stage 3: TrueList",
                                "check_name": "check_truelist_email",
                                "message": "Email is role-based (info@, support@, etc.)",
                                "failed_fields": ["email"]
                            })
                        else:
                            # Reject all other statuses (unknown, invalid, failed_*, etc.)
                            result = (False, {
                                "stage": "Stage 3: TrueList",
                                "check_name": "check_truelist_email",
                                "message": f"Email status '{status}' (only 'email_ok' accepted)",
                                "failed_fields": ["email"]
                            })
                        
                        # validation_cache[cache_key] = result
                        return result
        
        except EmailVerificationUnavailableError:
            # raise
            return False, "Pending"
        except asyncio.TimeoutError:
            if attempt < max_retries:
                print(f"   ⏳ TrueList timed out. Retrying in {retry_delay}s... ({attempt}/{max_retries})")
                await asyncio.sleep(retry_delay)
            else:
                # raise EmailVerificationUnavailableError("TrueList API timeout (all retries exhausted)")
                return False, "pending"
        except aiohttp.ClientError as e:
            if attempt < max_retries:
                print(f"   ⏳ Network error. Retrying in {retry_delay}s... ({attempt}/{max_retries})")
                await asyncio.sleep(retry_delay)
            else:
                # raise EmailVerificationUnavailableError(f"TrueList API network error: {str(e)}")
                return False, "pending"
        except Exception as e:
            if attempt < max_retries:
                print(f"   ⏳ Unexpected error. Retrying in {retry_delay}s... ({attempt}/{max_retries})")
                await asyncio.sleep(retry_delay)
            else:
                # raise EmailVerificationUnavailableError(f"TrueList API error: {str(e)}")
                return False, "pending"

def sn71_update_person_emailcheck(email, email_check):
    conn = psycopg.connect(
        dbname="mydb",
        user="myuser",
        password="strongpassword",
        host="95.217.116.91",
        port=5432
    )
    
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sn71_person
                SET email_check = %s
                WHERE email = %s
                """,
                (int(email_check), email)
            )
    
    return

if __name__ == "__main__":
    conn = psycopg.connect(
        dbname="mydb",
        user="myuser",
        password="strongpassword",
        host="95.217.116.91",
        port=5432,
        row_factory=psycopg.rows.dict_row,  # 👈 sanity saver
    )

    sql = """
    SELECT *
    FROM sn71_person
    WHERE
        seen is NULL
        AND lead_check is NULL
        -- AND email_check is NULL
        AND email_check = 0
    """

    with conn.cursor() as cur:
        cur.execute(
            sql,
        )
        
        rows = cur.fetchall()

    conn.commit()
    conn.close()

    for row in rows:
        print (row['email'])
        lead = {'email': row['email']}
        status, result = asyncio.run(check_truelist_email(lead))
        
        # print (status)
        # exit()
        
        if status == True:
            print (f"   ✔️✔️✔️✔️✔️✔️✔️✔️✔️True")
            email_check = 1
        else:
            print (f"   ❌❌❌❌❌❌❌❌❌False")
            email_check = 0
        
        sn71_update_person_emailcheck(row['email'], email_check)