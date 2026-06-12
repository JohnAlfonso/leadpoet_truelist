

"""
Practical Example: How to Use validate_role_rule_based() in Your Code

This shows real-world usage patterns for extracting and using gt_role
"""

import sys
sys.path.append('/work/jnh/new_71/leadpoet')

from validator_models.stage4_helpers import validate_role_rule_based


# ============================================================================
# EXAMPLE 1: From Lead Data Dictionary
# ============================================================================
def example_from_lead_dict():
    """Extract gt_role from lead data dictionary"""
    print("\n" + "="*80)
    print("EXAMPLE 1: Extract gt_role from Lead Data Dictionary")
    print("="*80)
    
    # Your lead data (from CSV, database, API, etc.)
    lead = {
        'full_name': 'Emily Chen',
        'company': 'Google',
        'role': 'Product Manager',  # ← THIS IS gt_role
        'linkedin': 'https://www.linkedin.com/in/emily-chen',
        'email': 'emily@google.com',
        'city': 'Mountain View',
        'state': 'California'
    }
    
    # Mock search results (you already have this)
    search_results = [
        {
            'title': 'Emily Chen - Product Manager - Google',
            'snippet': 'Product Manager at Google...',
            'link': 'https://www.linkedin.com/in/emily-chen'
        }
    ]
    
    # Extract parameters
    gt_role = lead['role']              # ← GET gt_role HERE
    linkedin_url = lead['linkedin']
    full_name = lead['full_name']
    
    # Call the function
    passed, method = validate_role_rule_based(
        gt_role,
        search_results,
        linkedin_url,
        full_name
    )
    
    print(f"\n📋 Lead Data:")
    print(f"   {lead}")
    print(f"\n🎯 Extracted Parameters:")
    print(f"   gt_role      = '{gt_role}'")
    print(f"   linkedin_url = '{linkedin_url}'")
    print(f"   full_name    = '{full_name}'")
    print(f"\n✅ Validation Result:")
    print(f"   Passed  = {passed}")
    print(f"   Method  = {method}")


# ============================================================================
# EXAMPLE 2: From Different Field Names
# ============================================================================
def example_different_field_names():
    """Handle different field name variations"""
    print("\n" + "="*80)
    print("EXAMPLE 2: Handle Different Field Names")
    print("="*80)
    
    # Different data sources use different field names
    lead_variations = [
        {'full_name': 'John', 'role': 'Engineer', 'linkedin': 'url'},
        {'name': 'Jane', 'job_title': 'Manager', 'linkedin_url': 'url'},
        {'Full Name': 'Bob', 'Role': 'Director', 'Linkedin': 'url'},
    ]
    
    for lead in lead_variations:
        # Flexible extraction
        gt_role = (
            lead.get('role') or 
            lead.get('Role') or 
            lead.get('job_title') or 
            lead.get('Job_title') or 
            ''
        )
        
        print(f"\n   Lead: {lead}")
        print(f"   → gt_role = '{gt_role}'")


# ============================================================================
# EXAMPLE 3: With Error Handling
# ============================================================================
def example_with_error_handling():
    """Production-ready code with error handling"""
    print("\n" + "="*80)
    print("EXAMPLE 3: Production Code with Error Handling")
    print("="*80)
    
    def validate_lead_role(lead: dict, search_results: list) -> dict:
        """
        Validate a lead's role with proper error handling
        
        Returns:
            {
                'valid': bool,
                'method': str or None,
                'error': str or None
            }
        """
        try:
            # Extract gt_role with validation
            gt_role = lead.get('role', '').strip()
            
            if not gt_role:
                return {
                    'valid': False,
                    'method': None,
                    'error': 'Missing role field'
                }
            
            # Validate role format (avoid placeholders)
            invalid_roles = ['n/a', 'tbd', 'job title', 'title', 'role', 'none']
            if gt_role.lower() in invalid_roles:
                return {
                    'valid': False,
                    'method': None,
                    'error': f'Invalid role placeholder: {gt_role}'
                }
            
            # Extract other required fields
            linkedin_url = lead.get('linkedin', '').strip()
            full_name = lead.get('full_name', '').strip()
            
            if not linkedin_url or not full_name:
                return {
                    'valid': False,
                    'method': None,
                    'error': 'Missing required fields'
                }
            
            # Call validation function
            passed, method = validate_role_rule_based(
                gt_role,
                search_results,
                linkedin_url,
                full_name
            )
            
            return {
                'valid': passed,
                'method': method,
                'error': None if passed else 'Role not found in search results'
            }
            
        except Exception as e:
            return {
                'valid': False,
                'method': None,
                'error': f'Validation error: {str(e)}'
            }
    
    # Test cases
    test_leads = [
        {
            'full_name': 'Valid User',
            'role': 'Software Engineer',
            'linkedin': 'https://www.linkedin.com/in/valid'
        },
        {
            'full_name': 'Invalid User',
            'role': 'N/A',  # Invalid placeholder
            'linkedin': 'https://www.linkedin.com/in/invalid'
        },
        {
            'full_name': 'Missing Role User',
            'role': '',  # Empty role
            'linkedin': 'https://www.linkedin.com/in/missing'
        }
    ]
    
    search_results = [
        {
            'title': 'Valid User - Software Engineer - Company',
            'snippet': 'Software Engineer at Company',
            'link': 'https://www.linkedin.com/in/valid'
        }
    ]
    
    for lead in test_leads:
        result = validate_lead_role(lead, search_results)
        print(f"\n   Lead: {lead['full_name']}")
        print(f"   Role: '{lead['role']}'")
        print(f"   → Valid: {result['valid']}, Method: {result['method']}, Error: {result['error']}")


# ============================================================================
# EXAMPLE 4: Batch Processing Multiple Leads
# ============================================================================
def example_batch_processing():
    """Process multiple leads at once"""
    print("\n" + "="*80)
    print("EXAMPLE 4: Batch Processing Multiple Leads")
    print("="*80)
    
    # Multiple leads from your data source
    leads = [
        {
            'full_name': 'Alice Smith',
            'role': 'Software Engineer',
            'linkedin': 'https://www.linkedin.com/in/alice-smith',
            'search_results': [
                {
                    'title': 'Alice Smith - Software Engineer - Google',
                    'link': 'https://www.linkedin.com/in/alice-smith'
                }
            ]
        },
        {
            'full_name': 'Bob Jones',
            'role': 'Product Manager',
            'linkedin': 'https://www.linkedin.com/in/bob-jones',
            'search_results': [
                {
                    'title': 'Bob Jones - VP of Sales - Microsoft',  # Mismatch!
                    'link': 'https://www.linkedin.com/in/bob-jones'
                }
            ]
        },
        {
            'full_name': 'Carol White',
            'role': 'Director of Engineering',
            'linkedin': 'https://www.linkedin.com/in/carol-white',
            'search_results': [
                {
                    'title': 'Carol White - Dir. of Engineering - Amazon',
                    'link': 'https://www.linkedin.com/in/carol-white'
                }
            ]
        }
    ]
    
    results = []
    
    for lead in leads:
        gt_role = lead['role']
        
        passed, method = validate_role_rule_based(
            gt_role,
            lead['search_results'],
            lead['linkedin'],
            lead['full_name']
        )
        
        results.append({
            'name': lead['full_name'],
            'claimed_role': gt_role,
            'passed': passed,
            'method': method
        })
    
    print(f"\n{'Name':<20} {'Claimed Role':<25} {'Passed':<10} {'Method':<15}")
    print("-" * 70)
    for r in results:
        status = '✅' if r['passed'] else '❌'
        print(f"{r['name']:<20} {r['claimed_role']:<25} {status:<10} {r['method'] or 'N/A':<15}")


# ============================================================================
# EXAMPLE 5: Integration with Stage 4 Pipeline
# ============================================================================
def example_stage4_integration():
    """Show how this fits into Stage 4 validation pipeline"""
    print("\n" + "="*80)
    print("EXAMPLE 5: Integration with Stage 4 Pipeline")
    print("="*80)
    
    print("""
    Stage 4 Pipeline Flow:
    =====================
    
    1. Get lead data
       ↓
    2. Run Q4 search: "{name}" "{company}" linkedin location
       ↓
    3. Optionally Q1 fallback: site:linkedin.com/in/{slug}
       ↓
    4. Validate URL match ✓
       ↓
    5. Validate name ✓
       ↓
    6. Validate company ✓
       ↓
    7. Validate location ✓
       ↓
    8. Validate role (THIS FUNCTION) ← You are here
       │
       ├─→ validate_role_rule_based(gt_role, search_results, linkedin_url, full_name)
       │   │
       │   ├─→ If PASS ✅: Done
       │   │
       │   └─→ If FAIL ❌: Fall back to LLM
       │       │
       │       └─→ validate_role_with_llm(...)
       │           │
       │           ├─→ If PASS ✅: Done
       │           │
       │           └─→ If FAIL ❌: Reject lead
       ↓
    9. Return validation result
    
    
    Your Code Location:
    ==================
    
    # In stage4_person_verification.py (line ~602):
    
    role = lead.get('role', '').strip()  # ← Extract gt_role from lead
    
    if role:
        role_passed, role_method = validate_role_rule_based(
            role,          # ← gt_role parameter
            all_results,   # ← You already have this
            linkedin_url,  # ← You already have this
            full_name      # ← You already have this
        )
        
        if role_passed:
            # ✅ Rule-based validation passed
            result['data']['role_verified'] = True
            result['data']['role_method'] = role_method
        else:
            # ❌ Rule-based failed → Try LLM fallback
            llm_result = validate_role_with_llm(...)
    """)


# ============================================================================
# RUN ALL EXAMPLES
# ============================================================================
if __name__ == "__main__":
    example_from_lead_dict()
    example_different_field_names()
    example_with_error_handling()
    example_batch_processing()
    example_stage4_integration()
    
    print("\n" + "="*80)
    print("✅ All examples completed!")
    print("="*80)
    print("\n📚 Key Takeaways:")
    print("   1. gt_role = lead['role']  ← The CLAIMED job title to verify")
    print("   2. It's a plain string (e.g., 'Software Engineer', 'VP Sales')")
    print("   3. Extract it from your lead data before calling the function")
    print("   4. Validate it's not empty or a placeholder (N/A, TBD, etc.)")
    print("   5. Pass it along with search_results, linkedin_url, full_name")
    print()
