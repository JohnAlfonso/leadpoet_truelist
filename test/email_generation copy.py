import re

def generate_work_emails(full_name, company_domain):
    """
    Generate possible work email addresses based on common business email patterns.
    
    Args:
        full_name (str): Full name of the person (e.g., "Bob Hale")
        company_domain (str): Company domain (e.g., "nationwide.com")
    
    Returns:
        list: List of possible email addresses sorted by most common patterns first
    """
    # Clean and split the name
    full_name = full_name.strip()
    name_parts = re.split(r'\s+', full_name)
    
    # Extract first and last name
    first_name = name_parts[0].lower() if len(name_parts) > 0 else ""
    last_name = name_parts[-1].lower() if len(name_parts) > 1 else ""
    
    # If there's only one name part, use it as both first and last
    if not last_name:
        last_name = first_name
    
    # Clean names: remove special characters, keep only letters
    first_name = re.sub(r'[^a-z]', '', first_name)
    last_name = re.sub(r'[^a-z]', '', last_name)
    
    if not first_name or not last_name:
        return []
    
    # Get initials and variations
    first_initial = first_name[0] if first_name else ""
    last_initial = last_name[0] if last_name else ""
    
    # Common prefixes for email addresses
    email_prefixes = []
    
    # 1. Starting with first name
    # Full first + last
    email_prefixes.append(f"{first_name}{last_name}")        # johndoe
    email_prefixes.append(f"{first_name}.{last_name}")       # john.doe
    email_prefixes.append(f"{first_name}_{last_name}")       # john_doe
    email_prefixes.append(f"{first_name}-{last_name}")       # john-doe
    
    # First name + last initial
    email_prefixes.append(f"{first_name}{last_initial}")     # johnd
    email_prefixes.append(f"{first_name}.{last_initial}")    # john.d
    email_prefixes.append(f"{first_name}_{last_initial}")    # john_d
    email_prefixes.append(f"{first_name}-{last_initial}")    # john-d
    
    # First initial + last name
    email_prefixes.append(f"{first_initial}{last_name}")     # jdoe
    email_prefixes.append(f"{first_initial}.{last_name}")    # j.doe
    email_prefixes.append(f"{first_initial}_{last_name}")    # j_doe
    email_prefixes.append(f"{first_initial}-{last_name}")    # j-doe
    
    # 2. Starting with last name
    # Last + first
    email_prefixes.append(f"{last_name}{first_name}")        # doejohn
    email_prefixes.append(f"{last_name}.{first_name}")       # doe.john
    email_prefixes.append(f"{last_name}_{first_name}")       # doe_john
    email_prefixes.append(f"{last_name}-{first_name}")       # doe-john
    
    # Last name + first initial
    email_prefixes.append(f"{last_name}{first_initial}")     # doej
    email_prefixes.append(f"{last_name}.{first_initial}")    # doe.j
    email_prefixes.append(f"{last_name}_{first_initial}")    # doe_j
    email_prefixes.append(f"{last_name}-{first_initial}")    # doe-j
    
    # Last initial + first name
    email_prefixes.append(f"{last_initial}{first_name}")     # djohn
    email_prefixes.append(f"{last_initial}.{first_name}")    # d.john
    email_prefixes.append(f"{last_initial}_{first_name}")    # d_john
    email_prefixes.append(f"{last_initial}-{first_name}")    # d-john
    
    # 3. Additional common patterns
    # First name only
    email_prefixes.append(first_name)                        # john
    
    # Last name only
    email_prefixes.append(last_name)                         # doe
    
    # First initial + last initial
    email_prefixes.append(f"{first_initial}{last_initial}")  # jd
    email_prefixes.append(f"{first_initial}.{last_initial}") # j.d
    
    # First name with middle initial (if available)
    if len(name_parts) > 2:
        middle_name = name_parts[1].lower()
        middle_initial = middle_name[0] if middle_name else ""
        middle_name = re.sub(r'[^a-z]', '', middle_name)
        
        if middle_name:
            # First + middle + last
            email_prefixes.append(f"{first_name}{middle_initial}{last_name}")    # johnjdoe
            email_prefixes.append(f"{first_name}.{middle_initial}.{last_name}")  # john.j.doe
            email_prefixes.append(f"{first_name}{middle_name}{last_name}")       # johnjamiedoe
            
            # First initial + middle initial + last name
            email_prefixes.append(f"{first_initial}{middle_initial}{last_name}") # jjdoe
    
    # Remove duplicates while preserving order
    unique_prefixes = []
    seen = set()
    for prefix in email_prefixes:
        if prefix and prefix not in seen:
            seen.add(prefix)
            unique_prefixes.append(prefix)
    
    # Create full email addresses
    emails = [f"{prefix}@{company_domain}" for prefix in unique_prefixes]
    
    return emails

def filter_and_rank_emails(full_name, company_domain, custom_patterns=None):
    """
    Generate and rank email addresses by likelihood.
    
    Args:
        full_name (str): Full name of the person
        company_domain (str): Company domain
        custom_patterns (list, optional): Additional custom patterns to try
    
    Returns:
        dict: Dictionary with ranked email lists
    """
    # Generate all possible emails
    all_emails = generate_work_emails(full_name, company_domain)
    
    # Split name for filtering
    name_parts = re.split(r'\s+', full_name.strip().lower())
    first_name = re.sub(r'[^a-z]', '', name_parts[0]) if name_parts else ""
    last_name = re.sub(r'[^a-z]', '', name_parts[-1]) if len(name_parts) > 1 else first_name
    
    # Categorize emails by pattern type
    categorized = {
        "most_common": [],  # First.Last, FirstLast, FLast
        "common": [],       # Other standard patterns
        "less_common": [],  # Last.First, etc.
        "simple": []        # First name only, last name only
    }
    
    for email in all_emails:
        local_part = email.split('@')[0]
        
        # Check patterns (order matters - most common first)
        if re.match(rf'^{first_name}[._-]?{last_name}$', local_part) or \
           re.match(rf'^{first_name}{last_name}$', local_part) or \
           re.match(rf'^{first_name[0]}{last_name}$', local_part):
            categorized["most_common"].append(email)
        elif re.match(rf'^{last_name}[._-]?{first_name}$', local_part) or \
             re.match(rf'^{last_name}{first_name}$', local_part) or \
             re.match(rf'^{last_name[0]}{first_name}$', local_part):
            categorized["common"].append(email)
        elif re.match(rf'^{first_name}[._-]?{last_name[0]}$', local_part) or \
             re.match(rf'^{last_name}[._-]?{first_name[0]}$', local_part):
            categorized["common"].append(email)
        elif local_part in [first_name, last_name]:
            categorized["simple"].append(email)
        else:
            categorized["less_common"].append(email)
    
    return categorized

def validate_email_pattern(email, full_name):
    """
    Validate if an email follows the name-email matching rule.
    
    Args:
        email (str): Email address to validate
        full_name (str): Full name for validation
    
    Returns:
        bool: True if email follows the rule
    """
    if '@' not in email:
        return False
    
    local_part = email.split('@')[0].lower()
    full_name = full_name.lower()
    
    # Split name into words
    name_words = re.findall(r'[a-z]+', full_name)
    
    # Check if any name word appears in the local part
    for word in name_words:
        if len(word) > 1 and word in local_part:
            return True
    
    # Check initials
    initials = ''.join([word[0] for word in name_words if word])
    if len(initials) >= 2 and initials in local_part:
        return True
    
    return False

def smart_email_generator(full_name, company_domain, max_results=10):
    """
    Smart email generator that provides the most likely email addresses.
    
    Args:
        full_name (str): Full name
        company_domain (str): Company domain
        max_results (int): Maximum number of results to return
    
    Returns:
        list: Most likely email addresses
    """
    categorized = filter_and_rank_emails(full_name, company_domain)
    
    # Combine in priority order
    all_sorted = []
    all_sorted.extend(categorized["most_common"])
    # TODO: Consider if we want to include less common patterns or simple patterns in the final list
    all_sorted.extend(categorized["common"])
    all_sorted.extend(categorized["less_common"])
    all_sorted.extend(categorized["simple"])
    
    # Remove duplicates
    unique_sorted = []
    seen = set()
    for email in all_sorted:
        if email not in seen:
            seen.add(email)
            unique_sorted.append(email)
    
    return unique_sorted[:max_results]

# Example usage and testing
if __name__ == "__main__":
    # Test with your example
    full_name = "David Winslow"
    company_domain = "nationwide.com"
    
    print("=" * 60)
    print(f"Generating work emails for: {full_name}")
    print(f"Company domain: {company_domain}")
    print("=" * 60)
    
    # Get smart predictions
    likely_emails = smart_email_generator(full_name, company_domain, max_results=30)
    
    print("\nMost likely email addresses:")
    for i, email in enumerate(likely_emails, 1):
        print(f"{i:2}. {email}")
        
        # check truelist
        status, result = asyncio.run(check_truelist_email(lead))
        
    