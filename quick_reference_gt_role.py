"""
Quick Reference: Two Ways to Get gt_role
=========================================
"""

# ============================================================================
# METHOD 1: Get gt_role from Lead Data (Standard Way)
# ============================================================================

def method1_from_lead_data():
    """When you have lead data with a claimed role"""
    
    # Your lead data
    lead = {
        'full_name': 'Jane Doe',
        'company': 'Google',
        'role': 'Software Engineer',  # ← Claimed role
        'linkedin': 'https://linkedin.com/in/jane-doe'
    }
    
    # Extract gt_role
    gt_role = lead['role']  # ← Simple!
    
    # Use it
    from validator_models.stage4_helpers import validate_role_rule_based
    
    passed, method = validate_role_rule_based(
        gt_role=gt_role,
        search_results=search_results,  # You already have this
        linkedin_url=lead['linkedin'],
        full_name=lead['full_name']
    )
    
    return passed, method


# ============================================================================
# METHOD 2: Extract gt_role from Search Results (Your Request)
# ============================================================================

def method2_from_search_results():
    """When you DON'T have lead data, only search results"""
    
    # What you have
    search_results = [
        {
            'title': 'Jane Doe - Software Engineer - Google | LinkedIn',
            'snippet': 'Software Engineer at Google...',
            'link': 'https://linkedin.com/in/jane-doe'
        }
    ]
    linkedin_url = 'https://linkedin.com/in/jane-doe'
    full_name = 'Jane Doe'
    company = 'Google'
    
    # Extract gt_role from search results
    from validator_models.stage4_helpers import extract_role_from_result, get_linkedin_id
    
    # Find the URL-matched result
    expected_lid = get_linkedin_id(linkedin_url)
    url_matched_result = None
    
    for result in search_results:
        result_lid = get_linkedin_id(result.get('link', ''))
        if result_lid == expected_lid:
            url_matched_result = result
            break
    
    # Extract role from it
    if url_matched_result:
        gt_role = extract_role_from_result(
            url_matched_result,
            full_name,
            company
        )
    else:
        gt_role = None
    
    # Use it
    if gt_role:
        from validator_models.stage4_helpers import validate_role_rule_based
        
        passed, method = validate_role_rule_based(
            gt_role=gt_role,
            search_results=search_results,
            linkedin_url=linkedin_url,
            full_name=full_name
        )
        
        return passed, method
    
    return False, None


# ============================================================================
# PRODUCTION CODE: Combined Approach
# ============================================================================

def get_gt_role(search_results, linkedin_url, full_name, company="", claimed_role=None):
    """
    Get gt_role from either claimed role or search results
    
    Priority:
    1. Use claimed_role if provided (verify scenario)
    2. Extract from search results (discover scenario)
    
    Args:
        search_results: Google search results
        linkedin_url: LinkedIn URL
        full_name: Person's name
        company: Company name (optional)
        claimed_role: Role from lead data (optional)
    
    Returns:
        str: gt_role to use
    """
    from validator_models.stage4_helpers import extract_role_from_result, get_linkedin_id
    
    # If claimed role provided, use it
    if claimed_role and claimed_role.strip():
        return claimed_role.strip()
    
    # Otherwise, extract from search results
    expected_lid = get_linkedin_id(linkedin_url)
    
    for result in search_results:
        result_lid = get_linkedin_id(result.get('link', ''))
        if result_lid == expected_lid:
            extracted_role = extract_role_from_result(result, full_name, company)
            if extracted_role:
                return extracted_role
    
    return ""


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    import sys
    sys.path.append('/work/jnh/new_71/leadpoet')
    from validator_models.stage4_helpers import validate_role_rule_based
    
    print("="*80)
    print("QUICK REFERENCE: Two Ways to Get gt_role")
    print("="*80)
    
    # Setup
    search_results = [
        {
            'title': 'Test User - Software Engineer - Company | LinkedIn',
            'snippet': 'Software Engineer at Company...',
            'link': 'https://linkedin.com/in/test-user'
        }
    ]
    linkedin_url = 'https://linkedin.com/in/test-user'
    full_name = 'Test User'
    company = 'Company'
    
    # ========================================================================
    # SCENARIO 1: Have Claimed Role (Standard)
    # ========================================================================
    print("\n" + "─"*80)
    print("SCENARIO 1: Have Claimed Role from Lead Data")
    print("─"*80)
    
    claimed_role = "Senior Software Engineer"
    
    gt_role = get_gt_role(
        search_results, linkedin_url, full_name, company,
        claimed_role=claimed_role  # ← Provide claimed role
    )
    
    print(f"Input:  claimed_role = '{claimed_role}'")
    print(f"Output: gt_role = '{gt_role}'")
    print(f"Source: Lead data")
    
    passed, method = validate_role_rule_based(
        gt_role, search_results, linkedin_url, full_name
    )
    print(f"Result: Passed = {passed}, Method = {method}")
    
    # ========================================================================
    # SCENARIO 2: Extract from Search (Your Request)
    # ========================================================================
    print("\n" + "─"*80)
    print("SCENARIO 2: Extract from Search Results (No Claimed Role)")
    print("─"*80)
    
    gt_role = get_gt_role(
        search_results, linkedin_url, full_name, company,
        claimed_role=None  # ← No claimed role, extract from search
    )
    
    print(f"Input:  No claimed role")
    print(f"Output: gt_role = '{gt_role}'")
    print(f"Source: Extracted from search results")
    
    passed, method = validate_role_rule_based(
        gt_role, search_results, linkedin_url, full_name
    )
    print(f"Result: Passed = {passed}, Method = {method}")
    
    # ========================================================================
    # SCENARIO 3: Compare Claimed vs Actual
    # ========================================================================
    print("\n" + "─"*80)
    print("SCENARIO 3: Compare Claimed vs Actual Role")
    print("─"*80)
    
    claimed = "Product Manager"
    actual = get_gt_role(
        search_results, linkedin_url, full_name, company,
        claimed_role=None  # Extract actual
    )
    
    print(f"Claimed: '{claimed}'")
    print(f"Actual:  '{actual}'")
    
    # Validate claimed against actual
    passed, method = validate_role_rule_based(
        claimed,  # ← Use claimed role as gt_role
        search_results, linkedin_url, full_name
    )
    print(f"Match:   {passed} ({method})")
    
    print("\n" + "="*80)
    print("✅ Quick Reference Complete!")
    print("="*80)
    
    print("""
📚 Summary:

1. FROM LEAD DATA (you have claimed role):
   gt_role = lead['role']

2. FROM SEARCH RESULTS (you only have search results):
   gt_role = get_gt_role(search_results, linkedin_url, full_name, company)

3. COMBINED (use claimed if available, else extract):
   gt_role = get_gt_role(
       search_results, linkedin_url, full_name, company,
       claimed_role=lead.get('role')  # Optional
   )

4. THEN VALIDATE:
   passed, method = validate_role_rule_based(
       gt_role, search_results, linkedin_url, full_name
   )
""")
