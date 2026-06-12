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
from datetime import datetime, timedelta, timezone
from Leadpoet.base.validator import BaseValidatorNeuron
from Leadpoet.protocol import LeadRequest
from validator_models.automated_checks import validate_lead_list as auto_check_leads, run_automated_checks
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
    
    extract_root_domain
)

from db_utils.sn71_db_manager import sn71_person_get_row, sn71_company_per_row

import psycopg
conn = psycopg.connect(
    dbname="mydb",
    user="myuser",
    password="strongpassword",
    host="95.217.116.91",
    port=5432
)

# def sanitize_prospect(prospect, miner_hotkey=None):
#     """
#     Sanitize and validate prospect fields + add regulatory attestations.
    
#     Task 1.2: Appends attestation metadata from data/regulatory/miner_attestation.json
#     to ensure every lead submission includes regulatory compliance information.
#     """

#     def strip_html(s):
#         return re.sub('<.*?>', '', html.unescape(str(s))) if isinstance(
#             s, str) else s

#     def valid_url(url):
#         return bool(re.match(r"^https?://[^\s]+$", url))

#     # Get email and full_name with fallback to legacy names for backward compatibility
#     email = prospect.get("email", prospect.get("Owner(s) Email", ""))
#     full_name = prospect.get("full_name", prospect.get("Owner Full name", ""))
    
#     sanitized = {
#         "business":
#         strip_html(prospect.get("business", prospect.get("Business", ""))),
#         "full_name":
#         strip_html(full_name),
#         "first":
#         strip_html(prospect.get("first", prospect.get("First", ""))),
#         "last":
#         strip_html(prospect.get("last", prospect.get("Last", ""))),
#         "email":
#         strip_html(email),  # Use consistent field name
#         "linkedin":
#         strip_html(prospect.get("linkedin", prospect.get("LinkedIn", ""))),
#         "website":
#         strip_html(prospect.get("website", prospect.get("Website", ""))),
#         "industry":
#         strip_html(prospect.get("industry", prospect.get("Industry", ""))),
#         "role":
#         strip_html(prospect.get("role", prospect.get("Title", ""))),
#         "sub_industry":
#         strip_html(
#             prospect.get("sub_industry", prospect.get("Sub Industry", ""))),
#         "region":
#         strip_html(prospect.get("region", prospect.get("Region", ""))),
#         "description":
#         strip_html(prospect.get("description", "")),
#         "phone_numbers":
#         prospect.get("phone_numbers", []),
#         "founded_year":
#         prospect.get("founded_year", prospect.get("Founded Year", "")),
#         "ownership_type":
#         strip_html(prospect.get("ownership_type", prospect.get("Ownership Type", ""))),
#         "company_type":
#         strip_html(prospect.get("company_type", prospect.get("Company Type", ""))),
#         "number_of_locations":
#         prospect.get("number_of_locations", prospect.get("Number of Locations", "")),
#         "socials":
#         prospect.get("socials", {}),
#         "source":
#         miner_hotkey  # Add source field
#     }

#     if not valid_url(sanitized["linkedin"]):
#         sanitized["linkedin"] = ""
#     if not valid_url(sanitized["website"]):
#         sanitized["website"] = ""

#     # Load miner's attestation from subnet-level regulatory directory
#     attestation_file = Path("data/regulatory/miner_attestation.json")
#     if attestation_file.exists():
#         try:
#             with open(attestation_file, 'r') as f:
#                 attestation = json.load(f)
#             terms_hash = attestation.get("terms_version_hash")
#             wallet_ss58 = attestation.get("wallet_ss58")
#         except Exception as e:
#             bt.logging.warning(f"Failed to load attestation file: {e}")
#             terms_hash = "NOT_ATTESTED"
#             wallet_ss58 = miner_hotkey or "UNKNOWN"
#     else:
#         # Should never happen if TASK 1.1 is working, but handle gracefully
#         bt.logging.warning("No attestation file found - miner should have accepted terms at startup")
#         terms_hash = "NOT_ATTESTED"
#         wallet_ss58 = miner_hotkey or "UNKNOWN"
    
#     # Add regulatory attestation fields (per-submission metadata)
#     sanitized.update({
#         # Miner identity & attestation
#         "wallet_ss58": wallet_ss58,
#         "submission_timestamp": datetime.now(timezone.utc).isoformat(),
#         "terms_version_hash": terms_hash,
        
#         # Boolean attestations (implicit from terms acceptance)
#         "lawful_collection": True,
#         "no_restricted_sources": True,
#         "license_granted": True,
        
#         # Source provenance (Task 1.3 - may be added later)
#         # These fields will be populated by process_generated_leads() in Task 1.3
#         "source_url": prospect.get("source_url", ""),
#         "source_type": prospect.get("source_type", ""),
        
#         # Optional: Licensed resale fields (Task 1.4)
#         "license_doc_hash": prospect.get("license_doc_hash", ""),
#         "license_doc_url": prospect.get("license_doc_url", ""),
#     })

#     return sanitized

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
        
        print (f"source_url: {source_url}")
        
        # Determine source type FIRST (needed for validation)
        source_type = determine_source_type(source_url, lead)
        
        print (f"source_type: {source_type}")
        
        # Validate source URL against regulatory requirements
        try:
            is_valid, reason = await validate_source_url(source_url, source_type)
            
            print (f"is_valid: {is_valid} | reason: {reason}")
            
            if not is_valid:
                bt.logging.warning(f"Invalid source URL: {source_url} - {reason}")
                continue
        except Exception as e:
            bt.logging.error(f"Error validating source URL {source_url}: {e}")
            continue
        
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

async def validate_lead(lead, use_db = False):
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
        
        # Use automated_checks for comprehensive validation
        # NEW: run_automated_checks returns (passed, automated_checks_data) with structured data
        
        print (mapped_lead)
        
        person = None
        companydb = None
        if use_db:
            person = sn71_person_get_row(email)
            if not person:
                reason = f"❌❌❌❌❌ {email} - fetch person failed ❌❌❌❌"
                return False, reason
            
            # print (f"person={person}")
            
            website = get_field(lead, 'website')
            companydb = sn71_company_per_row(extract_root_domain(website))
            if not companydb:
                reason = f"❌❌❌❌❌ {email} | {website} - fetch company failed ❌❌❌❌"
                return False, reason
            
            # print (f"companydb={companydb}")

        # exit()

        passed, automated_checks_data = await run_automated_checks(mapped_lead, use_db, person, companydb)
        
        return passed, automated_checks_data
        
        # Extract rejection_reason from structured data for backwards compatibility
        reason = automated_checks_data.get("rejection_reason") if not passed else None
        
        # Append automated_checks data to mapped_lead so it gets stored in validation_tracking
        mapped_lead["automated_checks"] = automated_checks_data

        # If standard validation passed, check if deep verification is needed
        # if passed and should_run_deep_verification(mapped_lead):
        if passed:
            print(f"🔬 Running deep verification on {email}")
            
            print (">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
            
            deep_results = await run_deep_verification(mapped_lead)
            
            print (deep_results)
            
            print (">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
            
            if not deep_results["passed"]:
                print(f"❌ Deep verification failed: {deep_results}")
                # Mark lead for manual review or reject
                lead["deep_verification_failed"] = True
                lead["deep_verification_results"] = deep_results
            
                # Return structured rejection reason 
                deep_reason = deep_results["checks"][0]["reason"] if deep_results.get("checks") else "unknown"
                return {
                    'is_legitimate': False,
                    'reason': {
                        "stage": "Deep Verification",
                        "check_name": "deep_verification",
                        "message": f"Deep verification failed: {deep_reason}",
                        "failed_fields": []
                    },
                    'deep_verification_results': deep_results,
                    'enhanced_lead': mapped_lead  # Include enhanced lead even on deep verification failure
                }
            else:
                bt.logging.info(f"✅ Deep verification passed")
                lead["deep_verification_passed"] = True
                lead["deep_verification_results"] = deep_results
                
                # If manual review required, flag it but don't fail
                if deep_results.get("manual_review_required"):
                    lead["manual_review_required"] = True
                    bt.logging.info(f"📋 Lead flagged for manual review")

        # IMPORTANT: Copy rep_score from mapped_lead back to original lead
        # The calling code reads from lead_blob.get("rep_score"), not from mapped_lead
        if "rep_score" in mapped_lead:
            lead["rep_score"] = mapped_lead["rep_score"]
        
        # Prepare validation result with enhanced lead data
        validation_result = {
            'is_legitimate': passed,
            'reason': reason,
            'enhanced_lead': mapped_lead  # Include enhanced lead with DNSBL/WHOIS data
        }
        
        # NOTE: Audit logging removed - validators should NOT write directly to Supabase.
        # All logging is handled by the gateway via POST /validate (TEE architecture).
        # The gateway stores evidence_blob in validation_evidence_private and logs to TEE buffer.
        
        return validation_result
        
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
    # lead = {
    #     'business': 'Micron Technology, Inc.', 
    #     'full_name': 'sanjay mehrotra', 
    #     'first': 'sanjay', 
    #     'last': 'mehrotra', 
    #     'email': 'sanjay.mehrotra@micron.com', 
    #     'linkedin': "https://www.linkedin.com/in/sanjay-mehrotra", 
    #     'website': 'https://micron.com',
    #     'industry': 'Hardware', 
    #     'role': 'President & CEO, Micron Technology', 
    #     # 'role': 'Principal Engineer', 
    #     'sub_industry': 'Semiconductor', 
    #     'country': 'USA',
    #     'state': 'Idaho',
    #     'city': 'Boise',
    #     'region': 'Boise, Idaho, USA', 
    #     'description': 'Micron Technology, Inc. is a global leader in memory and storage solutions, providing innovative products and technologies that enable the world to harness the power of data.', 
    #     'company_linkedin': 'https://www.linkedin.com/company/micron-technology',
    #     'phone_numbers': [], 
    #     'founded_year': '1978', 
    #     'ownership_type': 'Public', 
    #     'company_type': 'Corp', 
    #     'number_of_locations': '3',
    #     'employee_count': '10001',
    #     'socials': {
    #         'linkedin': "https://www.linkedin.com/in/sanjay-mehrotra", 
    #         'github': None, 
    #         'twitter': None, 
    #         'telegram': None, 
    #         'instagram': None
    #     },
    # }
    
    leads = [lead]
    validated_leads = asyncio.run(process_generated_leads(leads))
    
    # print (validated_leads)
    # exit ()
    
    # sanitize leads    
    miner_hotkey = "test_miner_hotkey"
    sanitized = [
        sanitize_prospect(p, miner_hotkey) for p in validated_leads
    ]
    
    if len(sanitized) == 0:
        return False
        
    lead_ = sanitized[0]
    
    result = asyncio.run(validate_lead(lead_, use_db))
    
    # validate_lead returns (bool, dict) when use_db=True, or a dict when errors occur
    if isinstance(result, tuple):
        passed, reason = result
    else:
        # Result is a dictionary with is_legitimate, reason, enhanced_lead
        passed = result.get('is_legitimate', False)
        reason = result.get('reason', 'Unknown error')
    
    print (passed, reason)
    
    return passed, reason

async def get_resp_score(business, website):
    
    total_score = 0
    
    lead = {
        'email': f'aa.bb@{website}',
        'business': business,
        'website': f'https://{website}',
    }
    
    checked, reason = await check_domain_age(lead)
    if not checked:
        return 0

    checked, reason = await check_dnsbl(lead)
    if not checked:
        return 0
    
    results = await asyncio.gather(
        check_wayback_machine(lead),
        check_sec_edgar(lead),
        check_whois_dnsbl_reputation(lead),
        check_gdelt_mentions(lead),
        check_companies_house(lead),
        return_exceptions=True  # Don't fail entire batch if one check fails
    )
    
    # Unpack results (handle exceptions gracefully)
    wayback_score, wayback_data = results[0] if not isinstance(results[0], Exception) else (0, {"error": str(results[0])})
    sec_score, sec_data = results[1] if not isinstance(results[1], Exception) else (0, {"error": str(results[1])})
    whois_dnsbl_score, whois_dnsbl_data = results[2] if not isinstance(results[2], Exception) else (0, {"error": str(results[2])})
    gdelt_score, gdelt_data = results[3] if not isinstance(results[3], Exception) else (0, {"error": str(results[3])})
    companies_house_score, companies_house_data = results[4] if not isinstance(results[4], Exception) else (0, {"error": str(results[4])})
    
    print (f"✅ wayback_score: {wayback_score}")
    print (f"✅ sec_score: {sec_score}")
    print (f"✅ whois_dnsbl_score: {whois_dnsbl_score}")
    print (f"✅ gdelt_score: {gdelt_score}")
    print (f"✅ companies_house_score: {companies_house_score}")
    
    total_rep_score = (
        wayback_score + sec_score + whois_dnsbl_score + gdelt_score +
        companies_house_score
    )
    
    return total_rep_score

def discover_companies(industry="Accommodation Services", country="", limit=100, offset=0):
    HUNTER_API_URL = "https://api.hunter.io/v2"
    HUNTER_API_KEY = "8760513a44059082b7566c546e4ca391eaef1fcb"
    url = f"{HUNTER_API_URL}/discover"
    try:

        data = {
            "industry": {"include": [industry]},
            # "headquarters_location": {"include": [{"country": "GB"}]},
            "limit": limit,
            "offset": offset
        }

        if country:
            data['headquarters_location'] = {"include": [{"country": country}]}
        
        params = {"api_key": HUNTER_API_KEY}
        response = requests.post(url, json=data, params=params)
    except Exception as e:
        print(f"discover_companies error: {e}")
        return {"errors": f"discover_companies error: {e}"}
    
    return response.json()

sql = """
INSERT INTO sn71_company (
    business, 
    website, 
    emails_count_personal, 
    emails_count_generic, 
    source,
    industry,
    country,
    resp_score
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""

def insert_db(companies, industry="", country=""):
        
    with conn:
        with conn.cursor() as cur:
            for company in companies:
                
                # print (company)
                # exit()
                
                business = company["organization"]
                website = company["domain"]
                emails_count_personal = company["emails_count"]["personal"]
                emails_count_generic = company["emails_count"]["generic"]
                # country = ""
                source = "hunter.io"
                # industry = ""
                resp_score = asyncio.run(get_resp_score(business, website))
                
                cur.execute(
                    sql,
                    (
                        business,
                        website,
                        emails_count_personal,
                        emails_count_generic,
                        source,
                        industry,
                        country,
                        resp_score
                    )
                )
                
                conn.commit()
    
    return ""

def get_country_from_hunter():
    
    industry = "Accommodation Services"
    country = "GB"
    LIMIT = 100
    
    # get the count of companies about INDUSTRY, COUNTRY
    companies_info = discover_companies(industry, country, 100, 0)
    results = companies_info['meta']['results']
    
    # get the companies
    for offset in range(0, results, 100):
        print (f"✅ discover_companies: industry={industry} | country={country} | limit={LIMIT} | offset={offset}")
        
        if offset == 0:
            continue
        
        # companies = discover_companies(industry, country, LIMIT, offset)
        # if 'errors' in companies:
        #     print (f"{industry} discover companies failed: skip")
        #     continue
        
        # insert_db(companies["data"], industry, country)
        
        # exit()
    
    return ""

if __name__ == "__main__":
    
    lead = {
        'business': 'Micron Technology, Inc.', 
        'full_name': 'sanjay mehrotra', 
        'first': 'sanjay', 
        'last': 'mehrotra', 
        'email': 'sanjay.mehrotra@micron.com', 
        'linkedin': "https://www.linkedin.com/in/sanjay-mehrotra", 
        'website': 'https://micron.com',
        'industry': 'Hardware', 
        'role': 'President & CEO, Micron Technology', 
        # 'role': 'Principal Engineer', 
        'sub_industry': 'Semiconductor', 
        'country': 'USA',
        'state': 'Idaho',
        'city': 'Boise',
        'region': 'Boise, Idaho, USA', 
        # 'description': 'Micron Technology, Inc. is a global leader in memory and storage solutions, providing innovative products and technologies that enable the world to harness the power of data.', 
        'company_linkedin': 'https://www.linkedin.com/company/micron-technology',
        'phone_numbers': [], 
        'founded_year': '1978', 
        'ownership_type': 'Public', 
        'company_type': 'Corp', 
        'number_of_locations': '3',
        'employee_count': '10001',
        'socials': {
            'linkedin': "https://www.linkedin.com/in/sanjay-mehrotra", 
            'github': None, 
            'twitter': None, 
            'telegram': None, 
            'instagram': None
        },
    }
    result = lead_validate(lead)
    print (f"==============> {result}")