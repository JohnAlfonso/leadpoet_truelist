"""
TrueList Batch API Test Script
===============================
Tests batch email verification using TrueList's batch API.

This script:
1. Fetches emails from sn71_person table (email_check = 0)
2. Submits batch to TrueList API
3. Polls for completion
4. Updates database with results

Usage:
    python sn71_truelist_batch_test.py

Dependencies:
    - validator_models/automated_checks.py (for batch functions)
    - PostgreSQL database with sn71_person table
"""

import asyncio
import os
import sys
from typing import List, Dict
from datetime import datetime

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

# Add parent directory to path to import from validator_models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from validator_models.automated_checks import (
    submit_truelist_batch,
    poll_truelist_batch,
    TRUELIST_API_KEY
)

from sn71_db_utils import (
    fetch_emails_from_db, 
    update_email_check_status,
    update_batch_results
)

load_dotenv()

# Override API key if not set in environment
if not TRUELIST_API_KEY:
    TRUELIST_API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJpZCI6ImQ2OTJiZDQ1LTExMDItNDYxNi1iYzFjLWZhNmNlYzI3NTUwNSIsImV4cGlyZXNfYXQiOm51bGx9.rN29HHXJhdWTMeQM3TMtGz-aPcaE0TD__rEWstrvUxM"
    # Inject into the module so submit_truelist_batch uses it
    import validator_models.automated_checks as ac
    ac.TRUELIST_API_KEY = TRUELIST_API_KEY

async def test_batch_verification(batch_size: int = 50):
    """
    Test TrueList batch API with emails from database.
    
    Args:
        batch_size: Number of emails to process in one batch
    """
    print("=" * 80)
    print("🧪 TrueList Batch API Test")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Batch size: {batch_size}")
    print("=" * 80)
    
    # Check API key
    if not TRUELIST_API_KEY:
        print("❌ ERROR: TRUELIST_API_KEY not configured in environment")
        print("   Set TRUELIST_API_KEY in .env file or environment variables")
        return
    
    print(f"✅ API Key configured: {TRUELIST_API_KEY[:20]}...")
    
    # Step 1: Fetch emails from database
    rows = fetch_emails_from_db(limit=batch_size)
    
    if not rows:
        print("⚠️  No emails found in database with email_check = 0")
        return
    
    emails = [row['email'] for row in rows]
    print(f"\n📧 Processing {len(emails)} emails:")
    for i, email in enumerate(emails[:5], 1):
        print(f"   {i}. {email}")
    if len(emails) > 5:
        print(f"   ... and {len(emails) - 5} more")
    
    # Step 2: Submit batch to TrueList
    print(f"\n{'='*80}")
    print("📤 Step 2: Submitting batch to TrueList API")
    print("=" * 80)
    
    try:
        batch_id = await submit_truelist_batch(emails)
        print(f"✅ Batch submitted successfully!")
        print(f"   Batch ID: {batch_id}")
    except Exception as e:
        print(f"❌ ERROR: Failed to submit batch: {e}")
        return
    
    # Step 3: Poll for results
    print(f"\n{'='*80}")
    print("⏳ Step 3: Polling for batch completion")
    print("=" * 80)
    
    try:
        results = await poll_truelist_batch(batch_id)
        print(f"✅ Batch completed successfully!")
        print(f"   Results received for {len(results)} emails")
    except Exception as e:
        print(f"❌ ERROR: Failed to poll batch: {e}")
        return
    
    # Step 4: Analyze results
    print(f"\n{'='*80}")
    print("📊 Step 4: Analyzing results")
    print("=" * 80)
    
    passed = sum(1 for r in results.values() if r.get("passed"))
    failed = sum(1 for r in results.values() if not r.get("passed") and not r.get("needs_retry"))
    retry = sum(1 for r in results.values() if r.get("needs_retry"))
    
    print(f"Results breakdown:")
    print(f"   ✅ Passed: {passed}/{len(emails)} ({100*passed/len(emails):.1f}%)")
    print(f"   ❌ Failed: {failed}/{len(emails)} ({100*failed/len(emails):.1f}%)")
    print(f"   🔄 Retry: {retry}/{len(emails)} ({100*retry/len(emails):.1f}%)")
    
    # Show sample results
    print(f"\n📋 Sample results (first 10):")
    for i, (email, result) in enumerate(list(results.items())[:10], 1):
        status = result.get("status", "unknown")
        passed_str = "✅ PASS" if result.get("passed") else "❌ FAIL"
        if result.get("needs_retry"):
            passed_str = "🔄 RETRY"
        
        print(f"   {i}. {email[:30]:<30} {passed_str:>10} ({status})")
    
    if len(results) > 10:
        print(f"   ... and {len(results) - 10} more")
    
    # Step 5: Update database
    print(f"\n{'='*80}")
    print("💾 Step 5: Updating database")
    print("=" * 80)
    
    update_batch_results(results)
    
    # Step 6: Show detailed failure reasons
    failures = {email: result for email, result in results.items() 
                if not result.get("passed") and not result.get("needs_retry")}
    
    if failures:
        print(f"\n{'='*80}")
        print("🔍 Failed Email Details")
        print("=" * 80)
        
        # Group by status
        status_groups = {}
        for email, result in failures.items():
            status = result.get("status", "unknown")
            if status not in status_groups:
                status_groups[status] = []
            status_groups[status].append(email)
        
        for status, emails_list in sorted(status_groups.items()):
            print(f"\n{status}: {len(emails_list)} emails")
            for email in emails_list[:3]:
                print(f"   - {email}")
            if len(emails_list) > 3:
                print(f"   ... and {len(emails_list) - 3} more")
    
    # Final summary
    print(f"\n{'='*80}")
    print("✅ Test completed successfully!")
    print("=" * 80)
    print(f"Total emails processed: {len(emails)}")
    print(f"Valid emails: {passed}")
    print(f"Invalid emails: {failed}")
    print(f"Needs retry: {retry}")
    print(f"Success rate: {100*passed/len(emails):.1f}%")
    print("=" * 80)


async def test_small_batch():
    """Quick test with 10 emails"""
    print("Running small batch test (10 emails)...")
    await test_batch_verification(batch_size=10)


async def test_medium_batch():
    """Medium test with 50 emails"""
    print("Running medium batch test (50 emails)...")
    await test_batch_verification(batch_size=50)


async def test_large_batch():
    """Large test with 200 emails"""
    print("Running large batch test (200 emails)...")
    await test_batch_verification(batch_size=200)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test TrueList Batch API")
    parser.add_argument(
        "--size",
        type=int,
        default=50,
        help="Batch size (number of emails to process)"
    )
    parser.add_argument(
        "--test",
        choices=["small", "medium", "large"],
        help="Run predefined test size (small=10, medium=50, large=200)"
    )
    
    args = parser.parse_args()
    
    if args.test == "small":
        asyncio.run(test_small_batch())
    elif args.test == "medium":
        asyncio.run(test_medium_batch())
    elif args.test == "large":
        asyncio.run(test_large_batch())
    else:
        asyncio.run(test_batch_verification(batch_size=args.size))
