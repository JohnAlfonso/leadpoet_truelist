import os
import sys
os.environ["PYTHONWARNINGS"] = "ignore::UserWarning"

import re
import time
import random
import requests
import textwrap
import numpy as np
import bittensor as bt
import argparse
import json
import html
import hashlib
from datetime import datetime, timedelta, timezone
from Leadpoet.base.validator import BaseValidatorNeuron
from Leadpoet.protocol import LeadRequest
from validator_models.automated_checks import validate_lead_list as auto_check_leads, run_automated_checks, run_stage0_2_checks, run_batch_automated_checks
from Leadpoet.base.utils.config import add_validator_args
import threading
from Leadpoet.base.utils import queue as lead_queue
from Leadpoet.base.utils import pool as lead_pool
import asyncio
from typing import List, Dict, Optional
from aiohttp import web
from Leadpoet.utils.cloud_db import (
    fetch_prospects_from_cloud,
    fetch_curation_requests,
    push_curation_result,
    push_miner_curation_request,
    fetch_miner_curation_result,
    push_validator_ranking,
)
from Leadpoet.utils.token_manager import TokenManager
from Leadpoet.utils.utils_lead_extraction import (
    get_email,
    get_website,
    get_company,
    get_industry,
    get_role,
    get_sub_industry,
    get_first_name,
    get_last_name,
    get_linkedin,
    get_location,
    get_field
)
from supabase import Client
import socket
from math import isclose
from pathlib import Path
import warnings

from typing import Dict, Any, Tuple, List, Optional
import asyncio

from neurons.miner import sanitize_prospect

from validator_models.automated_checks import (
    check_domain_age,
    check_dnsbl,
    check_wayback_machine, 
    check_sec_edgar, 
    check_whois_dnsbl_reputation, 
    check_gdelt_mentions, 
    check_companies_house,
    extract_root_domain,
    
    batch_validate_roles_llm
)

from Leadpoet.utils.cloud_db import check_email_duplicate

from gateway.api.submit import check_role_sanity, check_description_sanity, check_industry_taxonomy, check_linkedin_url_format
from gateway.utils.geo_normalize import normalize_location, validate_location, normalize_country, _normalize_state_for_validation, _normalize_for_validation

from psycopg.rows import dict_row
from psycopg.types.json import Json

import psycopg

async def process_generated_leads(leads: list) -> list:
        """
        Process and enrich leads with source provenance BEFORE sanitization.
        
        This function validates and enriches leads at the protocol level to ensure
        compliance with regulatory requirements. It cannot be bypassed by miners.
        
        Steps:
        1. Extract Website field from each lead
        2. Validate source URL against regulatory requirements
        3. Filter out invalid leads
        4. Determine source type (public_registry, company_site, etc.)
        5. Enrich lead with source_url and source_type
        
        Args:
            leads: Raw leads from lead generation model
            
        Returns:
            List of validated and enriched leads
        """
        from Leadpoet.utils.source_provenance import (
            validate_source_url,
            determine_source_type
        )
        
        validated_leads = []
        
        for lead in leads:
            # Extract website field (try multiple common field names)
            source_url = (
                lead.get("Website") or 
                lead.get("website") or 
                lead.get("Website URL") or
                lead.get("Company Website") or
                ""
            )
            
            if not source_url:
                bt.logging.warning(
                    f"Lead missing source URL, skipping: "
                    f"{lead.get('Business', lead.get('business', 'Unknown'))}"
                )
                continue
            
            # Determine source type FIRST (needed for validation)
            source_type = determine_source_type(source_url, lead)
            
            # exit()
            
            # Validate source URL against regulatory requirements
            try:
                is_valid, reason = await validate_source_url(source_url, source_type)
                
                # print (is_valid, reason)
                
                if not is_valid:
                    bt.logging.warning(f"Invalid source URL: {source_url} - {reason}")
                    continue
            except Exception as e:
                bt.logging.error(f"Error validating source URL {source_url}: {e}")
                continue
            
            # exit()
            
            # Enrich lead with provenance metadata
            lead["source_url"] = source_url
            lead["source_type"] = source_type
            
            validated_leads.append(lead)
        
        if validated_leads:
            bt.logging.info(
                f"✅ Source provenance: {len(validated_leads)}/{len(leads)} leads validated"
            )
        else:
            bt.logging.warning("⚠️ No leads passed source provenance validation")
        
        return validated_leads

def should_run_deep_verification(lead: Dict) -> bool:
    """
    Determine if lead should undergo deep verification.
    
    Returns True for:
    - 100% of licensed_resale submissions
    - 5% random sample of other submissions
    
    Deep verification includes:
    - License OCR validation (for licensed_resale)
    - Cross-domain authenticity checks
    - Behavioral anomaly scoring
    """
    source_type = lead.get("source_type", "")
    
    # Always verify licensed resale
    if source_type == "licensed_resale":
        bt.logging.info(f"🔬 Deep verification triggered: licensed_resale source")
        return True
    
    # 5% random sample for others
    if random.random() < 0.05:
        bt.logging.info(f"🔬 Deep verification triggered: random 5% sample")
        return True
    
    return False

async def verify_license_ocr(lead: Dict) -> Dict:
    """
    Validate license document via hash verification.
    
    Steps:
    1. Download document from license_doc_url
    2. Verify hash matches license_doc_hash (SHA-256)
    3. Flag for manual OCR review
    
    Future enhancement: Implement OCR text extraction to search for
    key terms (resale, redistribute, transfer, sub-license).
    
    Returns dict with:
    - passed: bool
    - check: str (check name)
    - reason: str (result description)
    - manual_review_required: bool (optional)
    """
    import hashlib
    import aiohttp
    
    license_url = lead.get("license_doc_url")
    license_hash = lead.get("license_doc_hash")
    
    if not license_url:
        return {
            "passed": False,
            "check": "license_ocr",
            "reason": "No license_doc_url provided for OCR verification"
        }
    
    if not license_hash:
        return {
            "passed": False,
            "check": "license_ocr",
            "reason": "No license_doc_hash provided"
        }
    
    try:
        # Download document
        bt.logging.info(f"   📥 Downloading license doc from: {license_url[:50]}...")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(license_url, timeout=30) as response:
                if response.status != 200:
                    return {
                        "passed": False,
                        "check": "license_ocr",
                        "reason": f"License doc unreachable: HTTP {response.status}"
                    }
                
                doc_content = await response.read()
        
        # Verify hash matches
        computed_hash = hashlib.sha256(doc_content).hexdigest()
        
        if computed_hash != license_hash:
            return {
                "passed": False,
                "check": "license_ocr",
                "reason": f"License doc hash mismatch (expected: {license_hash[:8]}..., got: {computed_hash[:8]}...)"
            }
        
        bt.logging.info(f"   ✅ License hash verified: {computed_hash[:16]}...")
        
        # TODO: Implement OCR text extraction (requires pytesseract or cloud OCR API)
        # For now, flag for manual review
        return {
            "passed": True,
            "check": "license_ocr",
            "reason": "Hash verified - flagged for manual OCR review",
            "manual_review_required": True,
            "license_hash": computed_hash,
            "license_url": license_url
        }
        
    except asyncio.TimeoutError:
        return {
            "passed": False,
            "check": "license_ocr",
            "reason": "License doc download timeout (>30s)"
        }
    except Exception as e:
        return {
            "passed": False,
            "check": "license_ocr",
            "reason": f"License verification error: {str(e)}"
        }

async def verify_cross_domain_authenticity(lead: Dict) -> Dict:
    """
    Verify entity-domain relationship authenticity.
    
    Checks:
    - Email domain should match company domain
    - Detects throwaway/temporary domains
    - Validates domain relationships
    
    This helps detect:
    - Spoofed email addresses
    - Temporary/disposable domains
    - Mismatched company-email relationships
    
    Returns dict with:
    - passed: bool
    - check: str (check name)
    - reason: str (result description)
    - severity: str (optional - "high" for critical mismatches)
    """
    from urllib.parse import urlparse
    
    email = get_email(lead)
    website = get_website(lead)
    company = get_company(lead)
    
    # If insufficient data, pass through (can't verify)
    if not email or not website:
        return {
            "passed": True,
            "check": "cross_domain",
            "reason": "Insufficient data for cross-domain verification"
        }
    
    # Extract domains
    email_domain = email.split("@")[1].lower() if "@" in email else ""
    
    # Parse website domain
    try:
        parsed_website = urlparse(website if website.startswith(('http://', 'https://')) else f'https://{website}')
        website_domain = parsed_website.netloc.lower()
        
        # Remove www. prefix for comparison
        if website_domain.startswith("www."):
            website_domain = website_domain[4:]
        if email_domain.startswith("www."):
            email_domain = email_domain[4:]
            
    except Exception as e:
        bt.logging.warning(f"   Failed to parse website domain: {website} - {e}")
        return {
            "passed": True,
            "check": "cross_domain",
            "reason": "Could not parse website domain"
        }
    
    # Check for throwaway/temporary domain indicators
    throwaway_indicators = [
        "-sales", "-marketing", "-temp", "tempmail", "guerrilla",
        "throwaway", "disposable", "fake", "test", "temporary"
    ]
    
    for indicator in throwaway_indicators:
        if indicator in email_domain:
            return {
                "passed": False,
                "check": "cross_domain",
                "reason": f"Email domain appears to be temporary: {email_domain}",
                "severity": "high"
            }
    
    # Check if domains match
    if email_domain == website_domain:
        return {
            "passed": True,
            "check": "cross_domain",
            "reason": "Email domain matches website domain"
        }
    
    # Check if they're related (subdomain or parent domain)
    if website_domain in email_domain or email_domain in website_domain:
        return {
            "passed": True,
            "check": "cross_domain",
            "reason": f"Related domains (email: {email_domain}, website: {website_domain})"
        }
    
    # Domains don't match - this could be legitimate (e.g., gmail.com for small business)
    # or could be suspicious. We'll flag but not fail for now.
    # In a stricter implementation, this could be a failure.
    return {
        "passed": True,  # Pass but log warning
        "check": "cross_domain",
        "reason": f"Email domain ({email_domain}) differs from website ({website_domain})",
        "severity": "low",
        "warning": True
    }

async def score_behavioral_anomalies(lead: Dict) -> Dict:
    """
    Score lead for behavioral anomalies.
    
    Checks for:
    - Excessive use of same source_url (possible scraping/automation)
    - Unlikely role-industry combinations
    - Statistical outliers
    
    Returns dict with:
    - passed: bool (True if anomaly_score < 0.7)
    - check: str (check name)
    - score: float (0-1, where 0=normal, 1=highly anomalous)
    - flags: list (descriptions of detected anomalies)
    - reason: str (summary)
    """
    anomaly_score = 0.0
    flags = []
    
    # Check 1: Duplicate source_url usage
    source_url = lead.get("source_url", "")
    if source_url:
        try:
            from Leadpoet.utils.cloud_db import get_supabase_client
            supabase = get_supabase_client()
            
            if supabase:
                # Query recent submissions with same source_url
                recent_cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                result = supabase.table("prospect_queue")\
                    .select("miner_hotkey, source_url")\
                    .eq("source_url", source_url)\
                    .gte("created_at", recent_cutoff)\
                    .execute()
                
                if result.data and len(result.data) > 10:
                    anomaly_score += 0.3
                    flags.append(f"Source URL used {len(result.data)} times in 24h")
                    bt.logging.warning(f"   ⚠️  High source_url reuse: {len(result.data)} times")
        except Exception as e:
            bt.logging.debug(f"   Could not check source_url duplicates: {e}")
    
    # Check 2: Role-industry mismatch
    # This is a simplified check - in production, use ML model or extensive mapping
    role = get_role(lead)
    industry = get_industry(lead)
    
    if role and industry:
        # Define obviously unlikely combinations
        unlikely_combinations = [
            ("Doctor", "Technology"),
            ("Doctor", "Software"),
            ("CTO", "Healthcare"),
            ("CTO", "Medical"),
            ("Nurse", "Finance"),
            ("Engineer", "Healthcare"),
            ("Surgeon", "Retail"),
        ]
        
        # Normalize for comparison
        role_normalized = role.upper()
        industry_normalized = industry.upper()
        
        for unlikely_role, unlikely_industry in unlikely_combinations:
            if unlikely_role.upper() in role_normalized and unlikely_industry.upper() in industry_normalized:
                anomaly_score += 0.2
                flags.append(f"Unlikely role-industry: {role} in {industry}")
                bt.logging.warning(f"   ⚠️  Unlikely combination: {role} in {industry}")
                break
    
    # Check 3: Missing critical fields (possible data quality issue)
    critical_fields = ["email", "company", "website"]
    missing_fields = [field for field in critical_fields if not lead.get(field)]
    
    if len(missing_fields) >= 2:
        anomaly_score += 0.1
        flags.append(f"Missing {len(missing_fields)} critical fields: {', '.join(missing_fields)}")
    
    # Determine pass/fail based on threshold
    threshold = 0.7
    passed = anomaly_score < threshold
    
    return {
        "passed": passed,
        "check": "anomaly_scoring",
        "score": anomaly_score,
        "flags": flags,
        "reason": f"Anomaly score: {anomaly_score:.2f} (threshold: {threshold})",
        "threshold": threshold
    }

async def run_deep_verification(lead: Dict) -> Dict:
    """
    Execute deep verification checks.
    
    Returns dict with:
    - passed: bool (overall pass/fail)
    - checks: list of individual check results
    - manual_review_required: bool (if flagged for admin review)
    """
    results = {
        "passed": True,
        "checks": [],
        "manual_review_required": False
    }
    
    # Check 1: License OCR validation (if applicable)
    if lead.get("source_type") == "licensed_resale":
        bt.logging.info("   🔍 Deep Check 1: License OCR validation")
        ocr_result = await verify_license_ocr(lead)
        results["checks"].append(ocr_result)
        
        if not ocr_result["passed"]:
            results["passed"] = False
            bt.logging.warning(f"   ❌ License OCR failed: {ocr_result['reason']}")
        else:
            bt.logging.info(f"   ✅ License OCR: {ocr_result['reason']}")
        
        if ocr_result.get("manual_review_required"):
            results["manual_review_required"] = True
    
    # Check 2: Cross-domain authenticity
    bt.logging.info("   🔍 Deep Check 2: Cross-domain authenticity")
    domain_result = await verify_cross_domain_authenticity(lead)
    results["checks"].append(domain_result)
    
    if not domain_result["passed"]:
        results["passed"] = False
        bt.logging.warning(f"   ❌ Cross-domain check failed: {domain_result['reason']}")
    else:
        bt.logging.info(f"   ✅ Cross-domain: {domain_result['reason']}")
    
    # Check 3: Behavioral anomaly scoring
    bt.logging.info("   🔍 Deep Check 3: Behavioral anomaly scoring")
    anomaly_result = await score_behavioral_anomalies(lead)
    results["checks"].append(anomaly_result)
    
    if not anomaly_result["passed"]:
        results["passed"] = False
        bt.logging.warning(f"   ❌ Anomaly check failed: {anomaly_result['reason']}")
    else:
        bt.logging.info(f"   ✅ Anomaly scoring: {anomaly_result['reason']}")
    
    return results

async def validate_lead(lead):
    """Validate a single lead using automated_checks. Returns pass/fail."""
    try:
        # Check for required email field first
        email = get_email(lead)
        if not email:
            return {
                'is_legitimate': False,
                'reason': {
                    "stage": "Pre-validation",
                    "check_name": "email_check",
                    "message": "Missing email",
                    "failed_fields": ["email"]
                },
                'enhanced_lead': lead  # Return original lead if no email
            }
        
        # Map your field names to what automated_checks expects
        mapped_lead = {
            "email": email,  # Map to "email" field
            "Email 1": email,  # Also map to "Email 1" as backup
            "Company": get_field(lead, 'business', 'website'),  # Map business -> Company
            "Website": get_field(lead, 'website', 'business'),  # Map to Website
            "website": get_field(lead, 'website', 'business'),  # Also lowercase
            "First Name": lead.get('first', ''),
            "Last Name": lead.get('last', ''),
            # Include any other fields that might be useful
            **lead  # Include all original fields too
        }

        passed, automated_checks_data = await run_automated_checks(mapped_lead)
        
        return passed, automated_checks_data
        
    except Exception as e:
        # Check if this is an EmailVerificationUnavailableError - if so, re-raise it
        from validator_models.automated_checks import EmailVerificationUnavailableError
        if isinstance(e, EmailVerificationUnavailableError):
            # Re-raise to propagate to process_sourced_leads_continuous
            raise
        
        bt.logging.error(f"Error in validate_lead: {e}")
        
        # Create structured rejection reason for error case
        error_rejection = {
            "stage": "Validation Error",
            "check_name": "exception",
            "message": f"Validation error: {str(e)}",
            "failed_fields": []
        }
        
        # NOTE: Audit logging removed - validators should NOT write directly to Supabase.
        # All logging is handled by the gateway via POST /validate (TEE architecture).
        
        return {
            'is_legitimate': False,
            'reason': error_rejection,
            'enhanced_lead': lead  # Return original lead on error
        }

def lead_validate(lead, use_db = False):
    
    leads = [lead]
    validated_leads = asyncio.run(process_generated_leads(leads))
    
    # sanitize leads    
    miner_hotkey = "test_miner_hotkey"
    sanitized = [
        sanitize_prospect(p, miner_hotkey) for p in validated_leads
    ]
    
    if len(sanitized) == 0:
        return False
        
    lead_ = sanitized[0]
    result = asyncio.run(validate_lead(lead_))
    
    # validate_lead returns (bool, dict) when use_db=True, or a dict when errors occur
    if isinstance(result, tuple):
        passed, reason = result
    else:
        # Result is a dictionary with is_legitimate, reason, enhanced_lead
        passed = result.get('is_legitimate', False)
        reason = result.get('reason', 'Unknown error')
    
    # print (passed, reason)
    
    return passed, reason

def gateway_check(lead_blob):
    
    #===== required fields check =====#
    REQUIRED_FIELDS = [
        "business",         # Company name
        "full_name",        # Contact full name
        "first",            # First name
        "last",             # Last name
        "email",            # Email address
        "role",             # Job title
        "website",          # Company website
        "industry",         # Primary industry (must match Crunchbase industry_group)
        "sub_industry",     # Sub-industry/niche (must match Crunchbase industry key)
        "country",          # Country (REQUIRED) - e.g., "United States", "Canada"
        "city",             # City (REQUIRED for all leads) - e.g., "San Francisco", "London"
        # "state" - REQUIRED for US only (validated in region validation section below)
        "linkedin",         # LinkedIn URL (person)
        "company_linkedin", # Company LinkedIn URL (for industry/sub_industry/description verification)
        # "source_url",       # Source URL where lead was found
        "description",      # Company description 
        "employee_count"    # Company size/headcount 
    ]
    
    missing_fields = []
    for field in REQUIRED_FIELDS:
        value = lead_blob.get(field)
        if not value or (isinstance(value, str) and not value.strip()):
            missing_fields.append(field)
    if missing_fields:
        return False, "required fields check false"
    
    
    #===== role check =====#
    role_raw = lead_blob.get("role", "").strip()
    full_name_for_check = lead_blob.get("full_name", "").strip()
    company_for_check = lead_blob.get("business", "").strip()
    city_for_check = lead_blob.get("city", "").strip()
    state_for_check = lead_blob.get("state", "").strip()
    country_for_check = lead_blob.get("country", "").strip()
    industry_for_check = lead_blob.get("industry", "").strip()

    # Call comprehensive role sanity check function (includes name/company/location/industry in role checks)
    error_code, error_message = check_role_sanity(
        role_raw, full_name_for_check, company_for_check,
        city=city_for_check, state=state_for_check, country=country_for_check,
        industry=industry_for_check
    )
    role_sanity_error = (error_code, error_message) if error_code else None
    if role_sanity_error:
        return False, "role check false"
    
    
    #===== description check =====#
    desc_raw = lead_blob.get("description", "").strip()

    # Call comprehensive description sanity check function
    desc_error_code, desc_error_message = check_description_sanity(desc_raw)
    desc_sanity_error = (desc_error_code, desc_error_message) if desc_error_code else None

    # Reject if any sanity check failed
    if desc_sanity_error:
        return False, "desc check false"
    
    
    #===== industry check =====#
    industry_raw = lead_blob.get("industry", "").strip()
    sub_industry_raw = lead_blob.get("sub_industry", "").strip()

    # Call industry taxonomy check
    ind_error_code, ind_error_message = check_industry_taxonomy(industry_raw, sub_industry_raw)

    if ind_error_code:
        return False, "industry check false"
    
    
    #===== country/state/city check =====#
    country_raw = lead_blob.get("country", "").strip()
    state = lead_blob.get("state", "").strip()
    city = lead_blob.get("city", "").strip()

    # Normalize country using geo_normalize (handles aliases + title case)
    country = normalize_country(country_raw)
    if country != country_raw:
        print(f"   📝 Country normalized: '{country_raw}' → '{country}'")

    # ALLOWED REGIONS: Only US cities and Dubai from UAE
    # Block all other countries at entry point
    country_lower = country.lower()
    is_allowed_region = (
        country_lower == "united states" or
        (country_lower == "united arab emirates" and city.lower().strip() == "dubai")
    )
    if not is_allowed_region:
        return False, "region 1 check false"
    
    # UAE has no states - reject if state is provided
    if country_lower == "united arab emirates" and state.strip():
        return False, "region 2 check false"
    
    # Validate location: country (199 valid), state (51 US states), city (exists in state/country)
    # print (city, state, country)
    is_valid, rejection_reason = validate_location(city, state, country)
    # print (is_valid, rejection_reason)
    if not is_valid:
        return False, "region 3 check false"
    
    if city and ',' in city:
        return False, "region 4 check false"
    
    if state and ',' in state:
        return False, "region 5 check false"
    
    
    #===== Validate employee_count format check =====#
    VALID_EMPLOYEE_COUNTS = [
        "0-1", "2-10", "11-50", "51-200", "201-500", 
        "501-1,000", "1,001-5,000", "5,001-10,000", "10,001+"
    ]
    
    employee_count = lead_blob.get("employee_count", "").strip()
    if employee_count not in VALID_EMPLOYEE_COUNTS:
        return False, "employee count check false"
    
    
    # ========================================
    # Verify source_type and source_url consistency
    # ========================================
    # source_type = lead_blob.get("source_type", "").strip()
    # source_url = lead_blob.get("source_url", "").strip()
    
    # if source_type == "proprietary_database" and source_url != "proprietary_database":
    #     return False, "source_url check false"
    
    
    # # Block LinkedIn URLs in source_url (miners should use source_type="linkedin" instead)
    # if "linkedin" in source_url.lower():
    #     return False, "source_url linkedin check false"
    
    
    # ========================================
    # Validate LinkedIn URL formats
    # ========================================
    linkedin_url = lead_blob.get("linkedin", "").strip()
    company_linkedin_url = lead_blob.get("company_linkedin", "").strip()

    linkedin_error_code, linkedin_error_message = check_linkedin_url_format(linkedin_url, company_linkedin_url)

    if linkedin_error_code:
        return False, "linkedin_url check false"
    
    return True, "OK"

def sn71_update_person_gatewaychek(email, seen):
    
    conn = psycopg.connect(
        dbname="mydb",
        user="myuser",
        password="strongpassword",
        host="95.217.116.91",
        port=5432,
    )
    
    sql = """
UPDATE sn71_person
SET
    seen = %s
WHERE
    email = %s
"""

    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                seen,
                email
            )
        )

    conn.commit()
    conn.close()
    
    return

if __name__ == "__main__":
    
    while True:
        conn = psycopg.connect(
            dbname="mydb",
            user="myuser",
            password="strongpassword",
            host="95.217.116.91",
            port=5432,
        )
        
        sql_sn71_person = """
        SELECT *
        FROM sn71_person
        WHERE
            lead_check = 1
            AND seen = 216
        """
        
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql_sn71_person)
            persons = cur.fetchall()
            print (len(persons))
        
        with open("file.txt", "a") as f:
            for person in persons:
                # result = asyncio.run(batch_validate_roles_llm([person['lead']['role']]))
                # if not result[person['lead']['role']]:
                #     sn71_update_person_gatewaychek(person['email'], 217)
                #     continue
                
                check, result = lead_validate(person['lead'])
                if not check:
                    print (">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>", person['email'], "FFFFFFF")
                    sn71_update_person_gatewaychek(person['email'], 219)
                    continue
                print ("==================================================================================================")
                # sn71_update_person_gatewaychek(person['email'], 216)
                
                # leads = [person['lead']]
                # validated_leads = asyncio.run(process_generated_leads(leads))
                
                # # sanitize leads    
                # miner_hotkey = "test_miner_hotkey"
                # sanitized = [
                #     sanitize_prospect(p, miner_hotkey) for p in validated_leads
                # ]
                
                # if len(sanitized) == 0:
                #     continue
                    
                # lead_ = sanitized[0]
                
                # check, reason = gateway_check(lead_)
                
                check, reason = gateway_check(person['lead'])
                if not check:
                    print ("===================>>>>>>>>>>>>>>>>>", person['email'], reason)
                    sn71_update_person_gatewaychek(person['email'], 215)
                else:
                    print ("==============>>>>>>>>>>>>", "OKK")
                    sn71_update_person_gatewaychek(person['email'], 218)
