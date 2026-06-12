import os
import sys
os.environ["PYTHONWARNINGS"] = "ignore::UserWarning"

import psycopg
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

from sn71_lead_vali import gateway_check

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
    
    return passed, reason

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

def valid_email_hash(email_hash):
    
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
        seen = 110
    """
    
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql_sn71_person)
        persons = cur.fetchall()        
        print (len(persons))

    for person in persons:
        
        if hashlib.sha256(person['email'].encode()).hexdigest() == email_hash:
        # if person['email'] == 'pkamel@baincapital.com':
            print (person['email'], hashlib.sha256(person['email'].encode()).hexdigest())
            # print (asyncio.run(batch_validate_roles_llm([person['lead']['role']])))
            
            # check, result = lead_validate(person['lead'])
            # if not check:
            #     print (">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>", person['email'])
            # print (check, result)

def check_duplicate_email():
    
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
        seen = 214 or seen = 216 or seen = 1 or seen = 110 or seen = 100
    """
    
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql_sn71_person)
        persons = cur.fetchall()
    
    possible_leads = []
    for person in persons:
        result = check_email_duplicate(person['email'])
        if not result:
            possible_leads.append(person['email'])

    print (len(possible_leads))

def check_215():
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
        seen = 215
    """
    
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql_sn71_person)
        persons = cur.fetchall()        
        print (len(persons))
        
    region3 = []
    for person in persons:
        check, reason = gateway_check(person['lead'])
        if not check:
            print ("===================>>>>>>>>>>>>>>>>>", person['email'], reason)
            if reason == "region 3 check false":
                region3.append(person['email'])
                
                
        else:
            print ("==============>>>>>>>>>>>>", "OKK")
            
    print (len(region3))

if __name__ == "__main__":
    print (f"{__name__} is called")
    
    email_hash = "398f38bb727e09408e5e1ba55c98e563883f8100a9f3cb787fb2bb7b7842dd88"
    valid_email_hash(email_hash)
    
    # check_duplicate_email()
    
    # check_215()
    