"""
Extract gt_role from Search Results
====================================
Shows how to DERIVE gt_role from search_results, linkedin_url, and full_name
(instead of getting it from lead data)

Use Case: You want to discover/extract the person's role from their LinkedIn profile
"""

import sys
sys.path.append('/work/jnh/new_71/leadpoet')

from validator_models.stage4_helpers import (
    extract_role_from_result,
    get_linkedin_id,
    validate_role_rule_based
)


def extract_gt_role_from_params(
    search_results: list,
    linkedin_url: str,
    full_name: str,
    company: str = ""
) -> dict:
    """
    Extract gt_role from search results instead of lead data
    
    Args:
        search_results: List of Google search results
        linkedin_url: Person's LinkedIn URL
        full_name: Person's name
        company: Person's company (optional, helps filter noise)
    
    Returns:
        {
            'gt_role': str or None,
            'source': str (which result it came from),
            'confidence': str (high/medium/low),
            'method': str (url_match, name_match, etc.)
        }
    """
    result = {
        'gt_role': None,
        'source': None,
        'confidence': 'low',
        'method': None
    }
    
    if not search_results:
        return result
    
    expected_lid = get_linkedin_id(linkedin_url)
    
    # Strategy 1: Extract from URL-matched result (HIGHEST confidence)
    for idx, search_result in enumerate(search_results):
        result_lid = get_linkedin_id(search_result.get('link', ''))
        
        if result_lid and expected_lid and result_lid == expected_lid:
            # Found the exact LinkedIn profile
            extracted_role = extract_role_from_result(
                search_result, 
                full_name, 
                company
            )
            
            if extracted_role:
                result['gt_role'] = extracted_role
                result['source'] = f"Result #{idx+1} (URL match): {search_result.get('link', '')}"
                result['confidence'] = 'high'
                result['method'] = 'url_match'
                return result
    
    # Strategy 2: Extract from name-matched results (MEDIUM confidence)
    for idx, search_result in enumerate(search_results):
        title = search_result.get('title', '').lower()
        snippet = search_result.get('snippet', '').lower()
        combined = f"{title} {snippet}"
        
        # Check if name appears in this result
        name_lower = full_name.lower()
        name_parts = name_lower.split()
        if not name_parts:
            continue
        
        first = name_parts[0]
        last = name_parts[-1] if len(name_parts) > 1 else first
        
        if first in combined or last in combined:
            # Name found in this result
            extracted_role = extract_role_from_result(
                search_result,
                full_name,
                company
            )
            
            if extracted_role:
                result['gt_role'] = extracted_role
                result['source'] = f"Result #{idx+1} (Name match): {search_result.get('link', '')}"
                result['confidence'] = 'medium'
                result['method'] = 'name_match'
                return result
    
    # Strategy 3: Parse LinkedIn title format (LOW confidence, fallback)
    for idx, search_result in enumerate(search_results):
        if 'linkedin.com' in search_result.get('link', '').lower():
            title = search_result.get('title', '')
            
            # Common LinkedIn title formats:
            # "Name - Role - Company | LinkedIn"
            # "Name | Role at Company | LinkedIn"
            
            if ' - ' in title and '|' in title:
                parts = title.split('|')[0].split(' - ')
                if len(parts) >= 2:
                    # parts[0] = Name, parts[1] = Potential Role
                    potential_role = parts[1].strip()
                    
                    # Basic validation (not the name, not the company)
                    name_lower = full_name.lower()
                    potential_lower = potential_role.lower()
                    
                    if (potential_lower not in name_lower and
                        name_lower not in potential_lower and
                        len(potential_role) >= 3 and
                        len(potential_role) <= 80):
                        
                        result['gt_role'] = potential_role
                        result['source'] = f"Result #{idx+1} (Title parse): {search_result.get('link', '')}"
                        result['confidence'] = 'low'
                        result['method'] = 'title_parse'
                        return result
    
    return result


# ============================================================================
# EXAMPLE 1: Extract Role from Search Results
# ============================================================================
def example_extract_role():
    """Extract role from search results instead of using lead data"""
    print("\n" + "="*80)
    print("EXAMPLE 1: Extract gt_role from Search Results")
    print("="*80)
    
    # You have these parameters
    full_name = "Sarah Johnson"
    linkedin_url = "https://www.linkedin.com/in/sarah-johnson"
    company = "Meta"
    
    search_results = [
        {
            'title': 'Sarah Johnson - Senior Product Manager - Meta | LinkedIn',
            'snippet': 'Senior Product Manager at Meta, leading the Instagram Growth team...',
            'link': 'https://www.linkedin.com/in/sarah-johnson'
        },
        {
            'title': 'Sarah Johnson | Meta',
            'snippet': 'Product Manager working on innovative solutions...',
            'link': 'https://www.meta.com/team/sarah-johnson'
        }
    ]
    
    # Extract gt_role from search results
    extraction = extract_gt_role_from_params(
        search_results,
        linkedin_url,
        full_name,
        company
    )
    
    print(f"\n📥 Input Parameters:")
    print(f"   full_name    = '{full_name}'")
    print(f"   linkedin_url = '{linkedin_url}'")
    print(f"   company      = '{company}'")
    print(f"   search_results = {len(search_results)} results")
    
    print(f"\n🎯 Extracted gt_role:")
    print(f"   gt_role     = '{extraction['gt_role']}'")
    print(f"   source      = {extraction['source']}")
    print(f"   confidence  = {extraction['confidence']}")
    print(f"   method      = {extraction['method']}")
    
    # Now you can use this extracted role for validation or other purposes
    if extraction['gt_role']:
        print(f"\n✅ SUCCESS: Extracted role from search results!")
        print(f"   You can now use: gt_role = '{extraction['gt_role']}'")


# ============================================================================
# EXAMPLE 2: Extract and Validate in One Flow
# ============================================================================
def example_extract_and_validate():
    """Extract role from search, then validate it against claimed role"""
    print("\n" + "="*80)
    print("EXAMPLE 2: Extract Role, Then Validate Against Claimed Role")
    print("="*80)
    
    # Scenario: Person claims "Product Manager" but profile says "Senior Product Manager"
    full_name = "John Smith"
    linkedin_url = "https://www.linkedin.com/in/john-smith"
    company = "Google"
    
    claimed_role = "Product Manager"  # What they claim
    
    search_results = [
        {
            'title': 'John Smith - Senior Product Manager - Google | LinkedIn',
            'snippet': 'Senior Product Manager at Google, 5 years experience...',
            'link': 'https://www.linkedin.com/in/john-smith'
        }
    ]
    
    # Extract actual role from profile
    extraction = extract_gt_role_from_params(
        search_results,
        linkedin_url,
        full_name,
        company
    )
    
    actual_role = extraction['gt_role']
    
    print(f"\n📋 Comparison:")
    print(f"   Claimed Role: '{claimed_role}'")
    print(f"   Actual Role:  '{actual_role}' (from LinkedIn)")
    
    # Validate claimed role against search results
    passed, method = validate_role_rule_based(
        claimed_role,
        search_results,
        linkedin_url,
        full_name
    )
    
    print(f"\n🔍 Validation Result:")
    print(f"   Does claimed role match profile? {passed}")
    print(f"   Method: {method}")
    
    if passed:
        print(f"   ✅ Claimed role is valid (close enough)")
    else:
        print(f"   ❌ Role mismatch detected!")


# ============================================================================
# EXAMPLE 3: Multiple Result Types
# ============================================================================
def example_multiple_result_types():
    """Handle different types of search results"""
    print("\n" + "="*80)
    print("EXAMPLE 3: Extract from Different Result Types")
    print("="*80)
    
    scenarios = [
        {
            'name': 'Emily Chen',
            'linkedin': 'https://www.linkedin.com/in/emily-chen',
            'company': 'Microsoft',
            'results': [
                {
                    'title': 'Emily Chen - Engineering Manager - Microsoft | LinkedIn',
                    'snippet': 'Engineering Manager at Microsoft...',
                    'link': 'https://www.linkedin.com/in/emily-chen'
                }
            ]
        },
        {
            'name': 'David Lee',
            'linkedin': 'https://www.linkedin.com/in/david-lee',
            'company': 'Amazon',
            'results': [
                {
                    'title': 'David Lee | LinkedIn',  # No role in title
                    'snippet': 'View David Lee\'s profile on LinkedIn. 500+ connections...',
                    'link': 'https://www.linkedin.com/in/david-lee'
                },
                {
                    'title': 'Meet Our Leadership - Amazon',
                    'snippet': 'David Lee is our VP of Engineering, leading the AWS team...',
                    'link': 'https://amazon.com/leadership'
                }
            ]
        },
        {
            'name': 'Lisa Wang',
            'linkedin': 'https://www.linkedin.com/in/lisa-wang',
            'company': 'Tesla',
            'results': [
                {
                    'title': 'Lisa Wang - Tesla',
                    'snippet': 'About Lisa Wang at Tesla...',
                    'link': 'https://www.tesla.com/team'
                }
            ]
        }
    ]
    
    for scenario in scenarios:
        extraction = extract_gt_role_from_params(
            scenario['results'],
            scenario['linkedin'],
            scenario['name'],
            scenario['company']
        )
        
        print(f"\n👤 {scenario['name']} ({scenario['company']})")
        print(f"   Extracted Role: '{extraction['gt_role']}'")
        print(f"   Confidence:     {extraction['confidence']}")
        print(f"   Source:         {extraction['source']}")


# ============================================================================
# EXAMPLE 4: Production Function - Complete Workflow
# ============================================================================
def get_role_from_search_results(
    search_results: list,
    linkedin_url: str,
    full_name: str,
    company: str = "",
    fallback_role: str = None
) -> str:
    """
    Production-ready function to get gt_role from search results
    
    Args:
        search_results: Google search results
        linkedin_url: LinkedIn profile URL
        full_name: Person's name
        company: Company name (optional)
        fallback_role: Role to use if extraction fails (optional)
    
    Returns:
        Extracted role string or fallback_role or empty string
    """
    extraction = extract_gt_role_from_params(
        search_results,
        linkedin_url,
        full_name,
        company
    )
    
    # Return extracted role if high/medium confidence
    if extraction['gt_role'] and extraction['confidence'] in ['high', 'medium']:
        return extraction['gt_role']
    
    # Return low confidence if it's the only option
    if extraction['gt_role'] and not fallback_role:
        return extraction['gt_role']
    
    # Use fallback if provided
    if fallback_role:
        return fallback_role
    
    return ""


def example_production_usage():
    """Production usage example"""
    print("\n" + "="*80)
    print("EXAMPLE 4: Production Usage - Complete Workflow")
    print("="*80)
    
    # Your actual parameters (what you have)
    search_results = [
        {
            'title': 'Alex Martinez - Staff Software Engineer - Netflix | LinkedIn',
            'snippet': 'Staff Software Engineer at Netflix, working on streaming infrastructure...',
            'link': 'https://www.linkedin.com/in/alex-martinez'
        }
    ]
    linkedin_url = "https://www.linkedin.com/in/alex-martinez"
    full_name = "Alex Martinez"
    company = "Netflix"
    
    print(f"\n📥 What You Have:")
    print(f"   - search_results: {len(search_results)} results")
    print(f"   - linkedin_url:   '{linkedin_url}'")
    print(f"   - full_name:      '{full_name}'")
    print(f"   - company:        '{company}'")
    
    # METHOD 1: Extract gt_role from search results
    gt_role = get_role_from_search_results(
        search_results,
        linkedin_url,
        full_name,
        company
    )
    
    print(f"\n🎯 What You Get:")
    print(f"   gt_role = '{gt_role}'")
    
    # Now use it with validate_role_rule_based
    print(f"\n✅ Ready to Use:")
    print(f"""
    # Now you can call the validation function:
    passed, method = validate_role_rule_based(
        gt_role="{gt_role}",
        search_results=search_results,
        linkedin_url=linkedin_url,
        full_name=full_name
    )
    """)
    
    # Actually run it
    passed, method = validate_role_rule_based(
        gt_role,
        search_results,
        linkedin_url,
        full_name
    )
    
    print(f"\n📊 Validation Result:")
    print(f"   Passed: {passed}")
    print(f"   Method: {method}")


# ============================================================================
# EXAMPLE 5: Comparison - Lead Data vs Search Extraction
# ============================================================================
def example_comparison():
    """Compare getting gt_role from lead data vs extracting from search"""
    print("\n" + "="*80)
    print("EXAMPLE 5: Lead Data vs Search Extraction Comparison")
    print("="*80)
    
    # Common parameters
    full_name = "Chris Taylor"
    linkedin_url = "https://www.linkedin.com/in/chris-taylor"
    company = "Apple"
    
    search_results = [
        {
            'title': 'Chris Taylor - Senior Software Engineer - Apple | LinkedIn',
            'snippet': 'Senior Software Engineer at Apple, iOS development...',
            'link': 'https://www.linkedin.com/in/chris-taylor'
        }
    ]
    
    print("\n" + "─"*80)
    print("METHOD 1: Get gt_role from Lead Data (Standard)")
    print("─"*80)
    
    lead = {
        'full_name': 'Chris Taylor',
        'company': 'Apple',
        'role': 'Software Engineer',  # What they submitted
        'linkedin': 'https://www.linkedin.com/in/chris-taylor'
    }
    
    gt_role_from_lead = lead['role']
    
    print(f"   Lead Data: {lead}")
    print(f"   gt_role = '{gt_role_from_lead}'")
    print(f"   Source: Claimed by user/lead")
    print(f"   Use Case: Verify if claimed role matches LinkedIn")
    
    print("\n" + "─"*80)
    print("METHOD 2: Extract gt_role from Search Results (Your Request)")
    print("─"*80)
    
    gt_role_from_search = get_role_from_search_results(
        search_results,
        linkedin_url,
        full_name,
        company
    )
    
    print(f"   Search Results: {len(search_results)} results")
    print(f"   gt_role = '{gt_role_from_search}'")
    print(f"   Source: Extracted from LinkedIn profile")
    print(f"   Use Case: Discover actual role, validate against claimed")
    
    print("\n" + "─"*80)
    print("📊 Comparison:")
    print("─"*80)
    print(f"   Claimed Role (from lead):  '{gt_role_from_lead}'")
    print(f"   Actual Role (from search): '{gt_role_from_search}'")
    
    # Validate claimed against actual
    passed, method = validate_role_rule_based(
        gt_role_from_lead,
        search_results,
        linkedin_url,
        full_name
    )
    
    print(f"\n   Validation: {passed} ({method})")
    print(f"   Analysis: Claimed 'Software Engineer' matches")
    print(f"             actual 'Senior Software Engineer' ✅")


# ============================================================================
# RUN ALL EXAMPLES
# ============================================================================
if __name__ == "__main__":
    example_extract_role()
    example_extract_and_validate()
    example_multiple_result_types()
    example_production_usage()
    example_comparison()
    
    print("\n" + "="*80)
    print("✅ All Examples Completed!")
    print("="*80)
    
    print("\n📚 Key Functions You Can Use:")
    print("""
    1. extract_gt_role_from_params(search_results, linkedin_url, full_name, company)
       → Returns: {'gt_role': str, 'source': str, 'confidence': str, 'method': str}
    
    2. get_role_from_search_results(search_results, linkedin_url, full_name, company)
       → Returns: str (just the role)
    
    3. Usage:
       gt_role = get_role_from_search_results(
           search_results=results,
           linkedin_url=url,
           full_name=name,
           company=company
       )
       
       # Then use it:
       passed, method = validate_role_rule_based(
           gt_role, search_results, linkedin_url, full_name
       )
    """)
    
    print("\n💡 When to Use Which Method:")
    print("   - Have lead data with claimed role? → Use lead['role'] as gt_role")
    print("   - Only have search results? → Extract gt_role from search results")
    print("   - Want to verify claimed role? → Extract actual role, then compare")
    print()
