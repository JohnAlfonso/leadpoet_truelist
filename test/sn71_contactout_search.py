import requests
import json
import gzip
import brotli
import re
import time
import random
from io import BytesIO
from datetime import datetime
from http.cookies import SimpleCookie
from urllib.parse import unquote

from sn71_db_utils import sn71_db_session_get_proxy, sn71_db_session_save_token, sn71_update_company_contactinfo
from sn71_contactout_process import process_persons, process_company

sleep_time = 10*60
MAX_HTTP_RETRIES = 3

# Your configuration
headers = {
    "authority": "contactout.com",
    "accept": "text/html, application/xhtml+xml",
    "accept-encoding": "gzip, deflate, br, zstd",  # We accept all encodings
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8,ja;q=0.7,zh-CN;q=0.6,zh;q=0.5",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "referer": "https://contactout.com/dashboard/search?company=Nationwide&companyIds=37441339&page=1&seniority=founder%7Cc_suite%7Cvice_president%7Cowner%7Cdirector",
    "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "x-inertia": "true",
    "x-inertia-version": "5f60677ab2a899ded344a64214712fe2",
    "x-requested-with": "XMLHttpRequest",
    "x-xsrf-token": "eyJpdiI6Imp6OU9IeUltZmVIRUF5RjkzYzBhMnc9PSIsInZhbHVlIjoiUzdwcHhzcEg5R0d3VFk3SjR3cEVJRG11elBuUTB2a1dDcHRWZURja3hpNXEwMVFlaGpYNm1nWTUwKzkzUVIrOGZaMkhGWElIcVkydlE3Skh4U0RRUTNsOHlDT0x2YUpKdEFIMDJPb0ZzQzdyTGR3NklsaTFtYWNHbTZxSW8xVFYiLCJtYWMiOiIzODBhZDM3ZGIwMGQyZTQ4OTE5NDcwYmJlZDY1ZmE2ZjkzMmRhYzI3MTg0YWQ4YWY2NDEwYjZmZjM4ZmQ0YTU5IiwidGFnIjoiIn0="
}

headers['x-xsrf-token'] = "eyJpdiI6InY2V2dsRmVveGtoeGRBNVVYbzNYQUE9PSIsInZhbHVlIjoiMkx1V3FaUDVib3JwZXpuN3ozbU9nQ3ovdlM1OEJYQjI0bi94VUp2R2JTSnJJREdkWUFTREk1VEtRQ25tU2hEMTVaQlNJb3dsMzU1ZnNrMUdrQ3pHZGdhN0U3SzQ5TnRmdElBY1pHeDlySmN0UmJvR2sybDNvYTVnVkVVSXpHTW0iLCJtYWMiOiIwZGZhY2ZjNWM0NDQ3NTdjOTQxZjkwMTU2NTI4OTNkZTQ3YzEzYmY2ZjdkYThkNzdhZjM1YTYxNGRiMWY3ZGJhIiwidGFnIjoiIn0="
cookies = {
    "XSRF-TOKEN": "eyJpdiI6InY2V2dsRmVveGtoeGRBNVVYbzNYQUE9PSIsInZhbHVlIjoiMkx1V3FaUDVib3JwZXpuN3ozbU9nQ3ovdlM1OEJYQjI0bi94VUp2R2JTSnJJREdkWUFTREk1VEtRQ25tU2hEMTVaQlNJb3dsMzU1ZnNrMUdrQ3pHZGdhN0U3SzQ5TnRmdElBY1pHeDlySmN0UmJvR2sybDNvYTVnVkVVSXpHTW0iLCJtYWMiOiIwZGZhY2ZjNWM0NDQ3NTdjOTQxZjkwMTU2NTI4OTNkZTQ3YzEzYmY2ZjdkYThkNzdhZjM1YTYxNGRiMWY3ZGJhIiwidGFnIjoiIn0%3D",
    "contactout_session": "eyJpdiI6IkdBUDR2eTMwWENMZXlhR2ZGaGhSelE9PSIsInZhbHVlIjoieUp5N1V0QzA2ZW9zWi8yWVFabXJqcE4yc2x5dVI2MDBlam1kSUt6UUZkemVHT215QTRTMVNhaHJLV1h1VGJ4dUN6ZmVha3hRZ2lpQmRhRi9mZjd1ZHdWcmozQlo4TW9rOTE3VmpWTXBBNWpxMGQ1blFMNGNkYnRFV1Y0NmdlbUYiLCJtYWMiOiIzNWFkYjg0ZmU0M2U4NmQwMWFhMGM0MmJmYTU1ZWNmZTA5ZmNlMmViNzdlOGU4MTVhZjBhNzIzYjY5YWE5M2ZkIiwidGFnIjoiIn0%3D"
}

def compare_date(expires, now):
    
    dt_str = expires
    ts = now

    # string -> datetime
    dt1 = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")

    # timestamp -> datetime
    dt2 = datetime.fromtimestamp(ts)

    print(dt1, dt2)

    if dt1 > dt2:
        return False
    elif dt1 < dt2:
        return True
    else:
        return True

def select_and_check_proxies(proxies):

    proxy = proxies[0]
    
    # print ("===========")
    # print (proxy)
    # print ("===========")
    # exit()
    
    expires = proxy['expires']
    now = time.time()
    
    is_expired = compare_date(str(expires), now)
    if is_expired:
        return False
    
    return proxy

def get_new_token_and_new_cookie_and_expires(response):
    # Use response.cookies (RequestsCookieJar) to reliably get all cookies
    # even when multiple Set-Cookie headers are present
    xsrf_token = response.cookies.get("XSRF-TOKEN", "")
    contactout_session = response.cookies.get("contactout_session", "")
    co_premium_user = response.cookies.get("co_premium_user", "")

    # Parse expires from Set-Cookie header (not exposed via .cookies)
    cookie = SimpleCookie()
    cookie.load(response.headers.get('Set-Cookie', ""))
    xsrf_expires = cookie["XSRF-TOKEN"]["expires"] if "XSRF-TOKEN" in cookie else ""
    contactout_expires = cookie["contactout_session"]["expires"] if "contactout_session" in cookie else ""

    return xsrf_token, xsrf_expires, contactout_session, contactout_expires, co_premium_user

def throttle(resp, proxy_username):
    
    xsrf_token, xsrf_expires, contactout_session, contactout_expires, co_premium_user = get_new_token_and_new_cookie_and_expires(resp)
    # print (unquote(xsrf_token))
    # print (xsrf_expires)
    # print (unquote(contactout_session), contactout_expires)
    # print (co_premium_user)
    
    # save new token
    sn71_db_session_save_token(xsrf_token, xsrf_expires, contactout_session, contactout_expires, co_premium_user, proxy_username)
    
    remaining = int(resp.headers.get("x-ratelimit-remaining", 0))
    limit = int(resp.headers.get("x-ratelimit-limit", 200))

    print(f"Rate: {remaining}/{limit}")
    # exit()

    if remaining < 210:
        print("Cooling down...")
        time.sleep(600)
    else:
        print ("**" * 10)
        time.sleep(random.uniform(5.0, 10.0))
        print ("*= " * 10)

def decode_response_content(response):
    """Handle different content encodings"""
    content_encoding = response.headers.get('content-encoding', '').lower()
    content = response.content
    
    # print(f"Content-Encoding: {content_encoding}")
    # print(f"Raw content length: {len(content)} bytes")
    
    try:
        if 'br' in content_encoding and hasattr(brotli, 'decompress'):
            print("Decoding brotli (br) compressed content...")
            decoded = brotli.decompress(content)
        elif 'gzip' in content_encoding:
            print("Decoding gzip compressed content...")
            decoded = gzip.decompress(content)
        elif 'deflate' in content_encoding:
            print("Decoding deflate compressed content...")
            decoded = BytesIO(content)
            import zlib
            decoded = zlib.decompress(content)
        else:
            # Try to auto-detect compression
            print("Trying to auto-detect compression...")
            try:
                # Try gzip first
                decoded = gzip.decompress(content)
                print("Auto-detected: gzip")
            except:
                try:
                    # Try brotli if available
                    if hasattr(brotli, 'decompress'):
                        decoded = brotli.decompress(content)
                        print("Auto-detected: brotli")
                    else:
                        decoded = content
                        print("Using raw content (brotli module not available)")
                except:
                    decoded = content
                    print("Using raw content")
        
        return decoded.decode('utf-8', errors='replace')
        
    except Exception as e:
        print(f"Error decoding content: {e}")
        # Try to decode as UTF-8 anyway
        try:
            return content.decode('utf-8', errors='replace')
        except:
            return str(content[:500]) + "..."

def make_request(url, params, proxy):
    """Make the HTTP request and handle compressed responses"""
    
    # proxy setting
    proxy_url = f"http://{proxy['proxy_user']}:{proxy['proxy_passwd']}@{proxy['proxy_ip']}:{proxy['proxy_port']}"
    proxies = {
        "http": proxy_url,
        "https": proxy_url
    }
    
    # header and cookie setting
    headers['x-xsrf-token'] = unquote(proxy['XSRF_TOKEN'])
    cookies = {
        "XSRF-TOKEN": proxy['XSRF_TOKEN'],
        "contactout_session": proxy['contactout_seesion'],
        "co_premium_user": proxy.get('co_premium_user', ''),
    }
    
    with requests.Session() as session:
        session.headers.update(headers)
        
        # Update cookies
        for key, value in cookies.items():
            session.cookies.set(key, value)
        
        for attempt in range(1, MAX_HTTP_RETRIES + 1):
            try:
                print("Making request to ContactOut...")
                response = session.get(
                    url,
                    params=params,
                    proxies=proxies,
                    timeout=30
                )
                
                print(f"\nStatus Code: {response.status_code}")
                print(f"Content-Type: {response.headers.get('content-type')}")
                
                if response.status_code == 200:
                    throttle(response, proxy['username'])
                    
                    # Handle compressed content
                    decoded_content = decode_response_content(response)
                    return True, decoded_content
                
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else min(60, attempt * 10)
                    print(f"❌❌❌❌ response.status_code = 429 (attempt {attempt}/{MAX_HTTP_RETRIES})")
                    if attempt < MAX_HTTP_RETRIES:
                        print(f"Retrying after {wait_seconds}s...")
                        time.sleep(wait_seconds)
                        continue
                    return False, ""
                
                if response.status_code in (500, 502, 503, 504):
                    wait_seconds = attempt * 3
                    print(f"❌❌❌❌ response.status_code = {response.status_code} (attempt {attempt}/{MAX_HTTP_RETRIES})")
                    if attempt < MAX_HTTP_RETRIES:
                        print(f"Transient server/proxy error. Retrying after {wait_seconds}s...")
                        time.sleep(wait_seconds)
                        continue
                    return False, ""
                
                print(f"❌❌❌❌ response.status_code = {response.status_code}")
                return False, ""
            except requests.exceptions.RequestException as e:
                print(f"Request error (attempt {attempt}/{MAX_HTTP_RETRIES}): {e}")
                if attempt < MAX_HTTP_RETRIES:
                    time.sleep(attempt * 2)
                    continue
                return False, ""  # Return tuple instead of None

def extract_person_and_process_with_company(company, companyIds, process):
    # request parameters
    company     = company       # "Nationwide"
    companyIds  = companyIds    # "37441339"
    page        = "1"
    # location    = "United States|Emiratele Arabe Unite"
    # seniority   = "founder|c_suite|vice_president|head|director|manager|senior"
    location = "United States"
    seniority = ""
    url = "https://contactout.com/dashboard/search"
    params = {
        "company": company,             # "Nationwide",
        "companyIds": companyIds,       # "37441339",
        "page": page,                   # "1",
        "location": location,           # "United State"
        "seniority": seniority,         # "founder%7Cc_suite%7Cvice_president"
    }
    
    meta = {}
    current_page = 0
    from_page = 0
    last_page = 0
    
    # select proxies and check proxy
    proxies = sn71_db_session_get_proxy(process)
    proxy = select_and_check_proxies(proxies)
    if not proxy:
        print ("❌❌❌❌ session is expired")
        return False
    
    # First search for gathering Meta infomation
    ret, content = make_request(url=url, params=params, proxy=proxy)
    
    if not ret:
        return False
    
    if content:
        print ("First Request... OK",)
        
        # print (content)
        
        data = json.loads(content)
        props = data.get('props', {})
        results = props.get('results', {})
        persons = results.get('data', [])
        # print ("--" * 100)
        # print (json.dumps(persons, indent=2))
        # print ("--" * 100)
        
        # get the meta info
        meta = results.get('meta', {})
        current_page = meta.get('current_page', 1)
        from_page = meta.get('from', 1)
        last_page = meta.get('last_page', 0)

        print (current_page, from_page, last_page)
    
    if last_page > 100:
        last_page = 100
    
    # exit()
    
    # Full search for company
    if current_page > 0:
        while current_page <= last_page:
            # search persons for company with meta info
            params = {
                "company": company,
                "companyIds": companyIds,
                "page": current_page,
                "location": location,
                "seniority": seniority,
            }
            
            # select proxies and check proxy
            proxies = sn71_db_session_get_proxy(process)
            proxy = select_and_check_proxies(proxies)
            if not proxy:
                print ("❌❌❌❌ session is expired")
                return False
            
            time.sleep(random.uniform(5.0, 10.0))    
            ret, content = make_request(url=url, params=params, proxy=proxy)
            if not ret:
                return False
            
            if content:
                
                print (f"current_page = {current_page} | last_page = {last_page}")
                
                data = json.loads(content)
                props = data.get('props', {})
                results = props.get('results', {})
                
                # get persons and process
                persons = results.get('data', [])
                process_persons(persons)
                
                # print ("*************************************************")
                # print ("*************************************************")
                # print (persons)
                # print ("*************************************************")
                # print ("*************************************************")
                
                
                # update meta info
                meta = results.get('meta', {})
                # print ("**************")
                # print (meta)
                current_page = meta.get('current_page', 1)
                from_page = meta.get('from', 1)
                last_page = meta.get('last_page', 0)
                
                if last_page > 100:
                    last_page = 100
                print (f"current_page = {current_page} | last_page = {last_page}")
                
                # add current_page
                current_page = current_page + 1
                print ("====>>>>>", current_page)
            else:
                return False
    else:
        print("\nRequest failed")
    print(f"🍀🍀🍀 {last_page} pages")
    return True

def call_contactout_template(process):
    companyName = "Baxter International"
    companyDomain = "nationwide.com"
    print("🏀🏀🏀🏀🏀")
    extract_company_from_contactout(companyName=companyName, companyDomain=companyDomain, process=process)

def extract_company_from_contactout(companyName, companyDomain, process):
    url = "https://contactout.com/dashboard/company"
    params = {
        "company": companyName,
        "domainUrl": companyDomain,
        "location": "",
        "headquarterOnly": "",
        "keyword": "",
        "industry": "",
        "employeeSize": "",
        "revenueMin": "",
        "revenueMax": "",
        "fundingDate": "",
        "fundingMin": "",
        "fundingMax": "",
        "yearFoundedFrom": "",
        "yearFoundedTo": "",
        "companyType": "",
        "SICCode": "",
        "linkedInFollowers": "",
        "linkedInUrl": "",
        "page": 1
    }
    
    # select proxies and check proxy
    proxies = sn71_db_session_get_proxy(process)
    proxy = select_and_check_proxies(proxies)
    if not proxy:
        print ("❌❌❌❌ session is expired")
        exit()
    
    ret, content = make_request(url=url, params=params, proxy=proxy)
    if not ret or not content:
        print ("❌❌ response content is NULL.")
        sn71_update_company_contactinfo({}, companyDomain)
        return False
    
    data = json.loads(content)
    props = data.get('props', {})
    results = props.get('results', {})
    data = results.get('data', [])
    if not data or len(data) == 0:
        print ("❌❌ company data is [].")
        sn71_update_company_contactinfo({}, companyDomain)
        return False
    
    print ("********" * 10)
    print (len(data))
    print ("********" * 10)
    
    is_found = False
    for companyData in data:
        if companyData['domain'] == companyDomain:
            # print (json.dumps(companyData, indent=2))
            res_process = process_company(companyData)
            if res_process:
                is_found = True
                break
    if not is_found:
        res_process = process_company(data[0], "exist")
        if not res_process:
            sn71_update_company_contactinfo({}, companyDomain)
    return True

def process_search_company_from_contactout(data):

    if not data or len(data) == 0:
        print ("❌❌ company data is [].")
        return False
    
    res_process = process_company(data, "search")
    return res_process


def search_companies_from_contactout(country, process, page=1, employee_size="1001_5000|5001_10000|10001",
                                     revenue_min=0, revenue_max=100,
                                     year_from="", year_to=""):
    """
    Search for companies on ContactOut by employee size, country, revenue range, and year founded.
    
    Args:
        country: Country filter (e.g., "United States")
        process: Process identifier for proxy management
        page: Page number for pagination
        employee_size: Employee size filter (default: "1001_5000")
                      Options: "1_10", "11_50", "51_200", "201_500", "501_1000", etc.
        revenue_min: Minimum revenue filter (in millions, default: 0)
        revenue_max: Maximum revenue filter (in millions, default: 100)
        year_from: Year founded from filter (e.g., "2012"), empty string to skip
        year_to:   Year founded to filter (e.g., "2012"), empty string to skip
    
    Returns:
        tuple: (success, companies_list, meta_info)
    """
    url = "https://contactout.com/dashboard/company"
    # location = "California|New York|Texas|Florida|Illinois|Pennsylvania|Ohio|Georgia|North Carolina|Michigan"
    location = "United States"
    params = {
        "company": "",
        "domainUrl": "",
        "location": country,
        "headquarterOnly": "",
        "keyword": "",
        "industry": "",
        "employeeSize": employee_size,  # Filter by employee size
        # "revenueMin": str(revenue_min),
        # "revenueMax": str(revenue_max),
        "revenueMin": "",
        "revenueMax": "",
        "fundingDate": "",
        "fundingMin": "",
        "fundingMax": "",
        "yearFoundedFrom": str(year_from),
        "yearFoundedTo": str(year_to),
        "companyType": "",
        "SICCode": "",
        "linkedInFollowers": "",
        "linkedInUrl": "",
        "page": page
    }
    print(f"🎠🎠🎠🎠🎠 - {employee_size}")
    # Get proxy
    proxies = sn71_db_session_get_proxy(process)
    proxy = select_and_check_proxies(proxies)
    if not proxy:
        print("❌ No valid proxy available")
        return False, [], {}
    
    # Make request
    ret, content = make_request(url, params, proxy)
    if not ret or not content:
        return False, [], {}
    
    # Parse response
    try:
        data = json.loads(content)
        props = data.get('props', {})
        results = props.get('results', {})
        companies = results.get('data', [])
        meta = results.get('meta', {})
        
        print(f"✅ Found {len(companies)} companies on page {page}")
        return True, companies, meta
    except Exception as e:
        print(f"❌ Error parsing company search response: {e}")
        return False, [], {}

# Main execution
if __name__ == "__main__":
    print("=" * 60)
    print("ContactOut Request with Compression Handling")
    print("=" * 60)
    
    # company = "Nationwide"
    # companyIds = "37441339"
    # extract_person_and_process_with_company(company, companyIds)
    
    # companyName = "Baxter International"
    # companyDomain = "nationwide.com"
    # extract_company_from_contactout(companyName=companyName, companyDomain=companyDomain)