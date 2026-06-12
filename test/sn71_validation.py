import os
import sys
import json
import asyncio

from Leadpoet.utils.source_provenance import validate_source_url
from validator_models.automated_checks import (
    check_head_request,
    check_domain_age,
    check_mx_record,
    check_spf_dmarc,
    check_dnsbl
)

async def vali_check_company_base(website):
    
    # STEP1: check_stage0_5/check_source_provenance
    source_url = website
    source_type = "company_site"
    is_valid, reason = await validate_source_url(source_url, source_type)
    if not is_valid:
        return False, f"validate_source_url failed - {reason}"
    
    # STEP2: check head request
    lead = { 'website': website }
    passed, rejection_reason = await check_head_request(lead)
    if not passed:
        return False, "check_head_request failed"
    
    # STEP3: check DNS
    results = await asyncio.gather(
        check_domain_age(lead),
        check_mx_record(lead),
        check_spf_dmarc(lead),
        return_exceptions=True
    )
    success = True
    check_names = ["check_domain_age", "check_mx_record", "check_spf_dmarc"]
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            success = False
            break
        
        passed, rejection_reason = result
        if not passed:
            success = False
            break
    if not success:
        return False, "check DNS"
    
    # STEP4: check_dnsbl
    lead["email"] = "abc@" + website
    passed, rejection_reason = await check_dnsbl(lead)
    if not passed:
        return False, "check_dnsbl"
    
    return True, "OK"
    
if __name__ == "__main__":
    print (f"{__name__} is called")
    
    website = "figma.com"
    ret, reason = asyncio.run(vali_check_company_base(website))
    print (ret, reason)