import requests
import json
import gzip
import brotli
import re
from io import BytesIO

# Your configuration
# url = "https://contactout.com/dashboard/search"
url = "https://contactout.com/dashboard/search?company=Nationwide&companyIds=37441339&location=United+States%7CEmiratele+Arabe+Unite&page=1&per_page=50&seniority=founder%7Cc_suite%7Cvice_president"
params = {
    "company": "Nationwide",
    "companyIds": "37441339",
    "page": "1",
    "location": "United+States",
    "seniority": "founder%7Cc_suite%7Cvice_president"
}

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
    "x-xsrf-token": "eyJpdiI6IkNqb0xFTTAxVzZXU3dQa2dLcnEvOVE9PSIsInZhbHVlIjoibEpEVUVYQUpRNGVBRHAvdkpVbkh5bVl2Y2RUSUgzcWxaRHI4ajJlWGI4WFNhaHM4dkVPcFlhcnhwQ3JMRmZlTTVXV1lhT050NmtMeklDblZVUXA3TENoR1VVb212V0VuZFp4eWh3MXIvK2ptY0dmMXFZWkdjM0tiN0ZyclF2b2EiLCJtYWMiOiJkM2Q4NDdhMjI3ODUzYmY4NzYwNjJkZTUyMTZjMmE4YjljMTQ0OGUzY2VlMjUyMmU3YjE4OWViYTFiNGYxZTk3IiwidGFnIjoiIn0="
}

cookies = {
    "XSRF-TOKEN": "eyJpdiI6IkNqb0xFTTAxVzZXU3dQa2dLcnEvOVE9PSIsInZhbHVlIjoibEpEVUVYQUpRNGVBRHAvdkpVbkh5bVl2Y2RUSUgzcWxaRHI4ajJlWGI4WFNhaHM4dkVPcFlhcnhwQ3JMRmZlTTVXV1lhT050NmtMeklDblZVUXA3TENoR1VVb212V0VuZFp4eWh3MXIvK2ptY0dmMXFZWkdjM0tiN0ZyclF2b2EiLCJtYWMiOiJkM2Q4NDdhMjI3ODUzYmY4NzYwNjJkZTUyMTZjMmE4YjljMTQ0OGUzY2VlMjUyMmU3YjE4OWViYTFiNGYxZTk3IiwidGFnIjoiIn0%3D",
    "contactout_session": "eyJpdiI6IlM0WW5TaUlKZXhCSnhnK3g1VHFOQVE9PSIsInZhbHVlIjoibDFlQUZEVFBIR2FEbUl1bjhaNW44SUpsNkh4NTNkdk5iTzZ3UlF5cEpaWGR1NEJRVDZWWEdHemV2ZytaVHFtS2t1YmsvQmNmM1lndzFLSUs1dEZPeTFTb3U0amU5bmI1UFEvb0pyQk5rUGhjSGJzL0tFVnVSOW13TDZtOTdHYzciLCJtYWMiOiI2MmZhNzQ1YTUzNGJkOWVmYzU1YzViYWJiMmVhNmNlOTdiYzk2OTY1NWVkZmQ2MDhmN2JmOTlhOGI2OTRhOGQ3IiwidGFnIjoiIn0%3D"
}

def decode_response_content(response):
    """Handle different content encodings"""
    content_encoding = response.headers.get('content-encoding', '').lower()
    content = response.content
    
    print(f"Content-Encoding: {content_encoding}")
    print(f"Raw content length: {len(content)} bytes")
    
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

def make_request():
    """Make the HTTP request and handle compressed responses"""
    session = requests.Session()
    session.headers.update(headers)
    
    # Update cookies
    for key, value in cookies.items():
        session.cookies.set(key, value)
    
    try:
        print("Making request to ContactOut...")
        response = session.get(url, timeout=30)
        
        print(f"\nStatus Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type')}")
        print(f"Content-Encoding: {response.headers.get('content-encoding', 'none')}")
        
        # Handle compressed content
        decoded_content = decode_response_content(response)
        
        # Save the decoded content
        with open('contactout_decoded_response.txt', 'w', encoding='utf-8') as f:
            f.write(decoded_content)
        print(f"\nDecoded response saved to 'contactout_decoded_response.txt'")
        
        # Also save raw bytes for inspection
        with open('contactout_raw_response.bin', 'wb') as f:
            f.write(response.content)
        print(f"Raw response saved to 'contactout_raw_response.bin'")
        
        # Analyze the decoded content
        analyze_decoded_content(decoded_content, response)
        
        return decoded_content
        
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return None

def analyze_decoded_content(content, response):
    """Analyze the decoded content"""
    print(f"\nDecoded content length: {len(content)} characters")
    
    # Show first 500 characters
    print(f"\nFirst 500 characters:")
    print(content[:500])
    
    # Check what type of content we have
    content_lower = content.lower()
    
    print ("=" * 100)
    # print (json.dumps(json.loads(content), indent=2))
    
    # data  = json.loads(content)
    print (json.dumps(json.loads(content)['props']['results']['meta'], indent=2))
    
    exit()
    
    # Check for common patterns
    if '<!doctype' in content_lower or '<html' in content_lower:
        print("\n✅ Decoded content is HTML")
        analyze_html_content(content)
        
    elif content.strip().startswith('{') or content.strip().startswith('['):
        print("\n✅ Decoded content appears to be JSON")
        try:
            data = json.loads(content)
            print(f"Successfully parsed JSON!")
            print(f"Type: {type(data)}")
            if isinstance(data, dict):
                print(f"Keys: {list(data.keys())}")
                # Check for actual data
                if 'data' in data:
                    print(f"Found 'data' field with {len(data['data']) if isinstance(data['data'], list) else 'unknown'} items")
                    return data
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print("Trying to find JSON within content...")
            find_json_in_content(content)
            
    elif 'inertia' in content_lower:
        print("\n✅ Inertia.js content detected")
        parse_inertia_content(content)
        
    elif 'login' in content_lower or 'sign in' in content_lower:
        print("\n⚠️  Login/Sign In page detected")
        print("You need to authenticate first")
        
    elif 'cloudflare' in content_lower or 'captcha' in content_lower:
        print("\n⚠️  Cloudflare or CAPTCHA protection detected")
        
    else:
        print("\n❓ Unknown content type")
        print("Trying to identify content...")
        
        # Check for binary patterns
        if len(content) < 1000 and any(ord(c) < 32 and c not in '\n\r\t' for c in content[:200]):
            print("Content contains binary/unprintable characters")
            
        # Try to extract any readable text
        readable = ''.join(c if 32 <= ord(c) < 127 else ' ' for c in content[:1000])
        print(f"\nFirst 1000 printable characters:")
        print(readable[:500])

def analyze_html_content(html):
    """Analyze HTML content"""
    print("\nAnalyzing HTML structure...")
    
    # Extract title
    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE)
    if title_match:
        print(f"Page Title: {title_match.group(1)}")
    
    # Check for Inertia.js
    if 'data-page=' in html:
        print("Found Inertia.js data-page attribute")
        parse_inertia_content(html)
    
    # Look for tables (common for contact data)
    tables = re.findall(r'<table[^>]*>', html, re.IGNORECASE)
    print(f"Found {len(tables)} table(s)")
    
    # Look for list items
    list_items = re.findall(r'<li[^>]*>', html, re.IGNORECASE)
    print(f"Found {len(list_items)} list item(s)")
    
    # Look for divs with data
    data_divs = re.findall(r'<div[^>]*data-[^=>]+[^>]*>', html, re.IGNORECASE)
    print(f"Found {len(data_divs)} div(s) with data attributes")

def parse_inertia_content(html):
    """Parse Inertia.js content"""
    print("\nParsing Inertia.js content...")
    
    # Look for data-page attribute
    pattern = r'data-page\s*=\s*["\']({.*?})["\']'
    matches = re.findall(pattern, html, re.DOTALL)
    
    if matches:
        print(f"Found {len(matches)} data-page attribute(s)")
        for i, match in enumerate(matches):
            if len(match) > 100:  # Reasonable minimum for JSON data
                print(f"\nTrying to parse data-page {i+1} (length: {len(match)})...")
                try:
                    data = json.loads(match)
                    print(f"✅ Successfully parsed!")
                    print(f"  Type: {type(data)}")
                    if isinstance(data, dict):
                        print(f"  Keys: {list(data.keys())}")
                        
                        # Check for props which often contain the actual data
                        if 'props' in data and isinstance(data['props'], dict):
                            print(f"  Props keys: {list(data['props'].keys())}")
                            
                            # Look for contact data
                            for key in ['contacts', 'results', 'data', 'leads']:
                                if key in data['props']:
                                    print(f"  Found '{key}' in props!")
                                    return data
                    return data
                except json.JSONDecodeError as e:
                    print(f"  JSON decode error: {e}")
                    # Try to fix common JSON issues
                    fixed = fix_json_string(match)
                    if fixed != match:
                        print("  Trying with fixed JSON...")
                        try:
                            data = json.loads(fixed)
                            print(f"  ✅ Fixed and parsed successfully!")
                            return data
                        except:
                            print("  Still not valid JSON")
    else:
        print("No data-page attribute found")

def fix_json_string(json_str):
    """Try to fix common JSON issues"""
    # Remove trailing commas
    fixed = re.sub(r',\s*}', '}', json_str)
    fixed = re.sub(r',\s*]', ']', fixed)
    
    # Fix single quotes (replace with double quotes for keys)
    fixed = re.sub(r"'\s*:\s*", '": ', fixed)
    fixed = re.sub(r"{\s*'", '{"', fixed)
    fixed = re.sub(r",\s*'", ',"', fixed)
    
    return fixed

def find_json_in_content(content):
    """Find JSON within content"""
    print("\nSearching for JSON patterns...")
    
    # Look for JSON objects
    json_pattern = r'(\{(?:[^{}]|(?R))*\})'
    matches = re.findall(json_pattern, content, re.DOTALL)
    
    if matches:
        print(f"Found {len(matches)} potential JSON objects")
        
        # Sort by length (longer ones are more likely to be real data)
        matches.sort(key=len, reverse=True)
        
        for i, match in enumerate(matches[:3]):  # Check top 3
            if 100 < len(match) < 50000:  # Reasonable size range
                print(f"\nTrying match {i+1} (length: {len(match)})...")
                try:
                    data = json.loads(match)
                    print(f"✅ Valid JSON!")
                    print(f"  Type: {type(data)}")
                    if isinstance(data, dict):
                        print(f"  Keys: {list(data.keys())[:10]}...")
                    return data
                except json.JSONDecodeError as e:
                    # Try with fixed JSON
                    fixed = fix_json_string(match)
                    if fixed != match:
                        try:
                            data = json.loads(fixed)
                            print(f"✅ Valid after fixing!")
                            return data
                        except:
                            pass
    else:
        print("No JSON patterns found")

# Alternative: Try without compression
def try_without_compression():
    """Try request without compression to see raw response"""
    print("\n" + "="*60)
    print("Trying request without compression...")
    print("="*60)
    
    # Remove accept-encoding to get raw response
    no_compress_headers = headers.copy()
    no_compress_headers['accept-encoding'] = 'identity'  # No compression
    
    session = requests.Session()
    session.headers.update(no_compress_headers)
    
    for key, value in cookies.items():
        session.cookies.set(key, value)
    
    try:
        response = session.get(url, params=params, timeout=30)
        print(f"Status: {response.status_code}")
        
        # Save raw response
        with open('contactout_no_compress.txt', 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"Response saved to 'contactout_no_compress.txt'")
        
        print(f"\nFirst 500 characters:")
        print(response.text[:500])
        
        return response.text
        
    except Exception as e:
        print(f"Error: {e}")
        return None

# Main execution
if __name__ == "__main__":
    print("=" * 60)
    print("ContactOut Request with Compression Handling")
    print("=" * 60)
    
    # First, try with automatic decompression
    content = make_request()
    
    if content:
        print("\n" + "="*60)
        print("DECODING COMPLETE")
        print("="*60)
        
        # If still getting binary/garbage, try without compression
        if len(content) < 100 or any(ord(c) < 32 and c not in '\n\r\t' for c in content[:100]):
            print("\nContent still appears to be binary/compressed")
            print("Trying alternative approach...")
            
            # Try without compression
            try_without_compression()
            
        print("\nNext steps:")
        print("1. Check 'contactout_decoded_response.txt' for readable content")
        print("2. If it's HTML, open it in a browser to see what's displayed")
        print("3. If it's JSON, we can parse the contact data from it")
        print("4. If it's still binary, we may need different headers/cookies")
    else:
        print("\nRequest failed")