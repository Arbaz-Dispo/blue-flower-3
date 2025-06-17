import requests
import json
from seleniumbase import SB
import time
from bs4 import BeautifulSoup
import re
import os
import uuid
import sys
from datetime import datetime

# API key must be provided via environment variable for security
API_KEY = os.getenv("SOLVECAPTCHA_API_KEY")
if not API_KEY:
    raise ValueError("SOLVECAPTCHA_API_KEY environment variable is required")

SOLVE_URL = "https://api.solvecaptcha.com/in.php"
RESULT_URL = "https://api.solvecaptcha.com/res.php"

def create_logs_folder():
    """Create logs folder if it doesn't exist"""
    if not os.path.exists("logs"):
        os.makedirs("logs")
        print("Created logs folder")

def save_screenshot(sb, file_number, request_type="screenshot", context=""):
    """Save screenshot from SeleniumBase browser"""
    try:
        create_logs_folder()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logs/{file_number}_{request_type}_{context}_{timestamp}.png"
        
        sb.save_screenshot(filename)
        print(f"[{file_number}] Saved screenshot to: {filename}")
        return filename
    except Exception as e:
        print(f"[{file_number}] Error saving screenshot: {str(e)}")
        return None

def save_failed_response(file_number, response, request_type="search"):
    """Save failed response HTML to logs folder"""
    try:
        create_logs_folder()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logs/{file_number}_{request_type}_failed_{timestamp}.html"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"<!-- File Number: {file_number} -->\n")
            f.write(f"<!-- Request Type: {request_type} -->\n")
            f.write(f"<!-- Status Code: {response.status_code} -->\n")
            f.write(f"<!-- Timestamp: {timestamp} -->\n")
            f.write(f"<!-- URL: {response.url} -->\n")
            f.write("<!-- Headers: -->\n")
            for header, value in response.headers.items():
                f.write(f"<!-- {header}: {value} -->\n")
            f.write("\n")
            f.write(response.text)
        
        print(f"[{file_number}] Saved failed response to: {filename}")
        return filename
    except Exception as e:
        print(f"[{file_number}] Error saving failed response: {str(e)}")
        return None

def save_successful_response(file_number, response, request_type="search"):
    """Save successful response HTML to logs folder for debugging"""
    try:
        create_logs_folder()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logs/{file_number}_{request_type}_success_{timestamp}.html"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"<!-- File Number: {file_number} -->\n")
            f.write(f"<!-- Request Type: {request_type} -->\n")
            f.write(f"<!-- Status Code: {response.status_code} -->\n")
            f.write(f"<!-- Timestamp: {timestamp} -->\n")
            f.write(f"<!-- URL: {response.url} -->\n")
            f.write("<!-- Headers: -->\n")
            for header, value in response.headers.items():
                f.write(f"<!-- {header}: {value} -->\n")
            f.write("\n")
            f.write(response.text)
        
        print(f"[{file_number}] Saved successful response to: {filename}")
        return filename
    except Exception as e:
        print(f"[{file_number}] Error saving successful response: {str(e)}")
        return None

def solve_recaptcha_v2(sitekey, pageurl):
    """Solve reCAPTCHA v2 using solvecaptcha.com API"""
    try:
        # Submit captcha
        payload = {
            'key': API_KEY,
            'method': 'userrecaptcha',
            'googlekey': sitekey,
            'pageurl': pageurl,
            'json': '1'
        }
        
        print("Submitting reCAPTCHA to API...")
        response = requests.post(SOLVE_URL, data=payload)
        response_data = response.json()
        
        if response_data.get('status') != 1:
            raise Exception(f"Failed to submit captcha: {response_data}")
            
        request_id = response_data['request']
        print(f"reCAPTCHA submitted successfully. Request ID: {request_id}")
        
        # Wait for solution
        max_attempts = 120  # 2 minutes maximum wait time (120 seconds)
        attempts = 0
        
        while attempts < max_attempts:
            time.sleep(1)  # Check every second instead of every 5 seconds
            result_payload = {
                'key': API_KEY,
                'action': 'get',
                'id': request_id,
                'json': '1'
            }
            
            result = requests.get(RESULT_URL, params=result_payload)
            result_data = result.json()
            
            if result_data.get('status') == 1:
                print("reCAPTCHA solved successfully!")
                print(result_data['request'])
                return result_data['request']  # This is the token
            
            attempts += 1
            print(f"Waiting for solution... Attempt {attempts}/{max_attempts} ({attempts}s elapsed)")
            
        raise Exception("Timeout waiting for captcha solution")
        
    except Exception as e:
        print(f"Error solving reCAPTCHA: {str(e)}")
        raise

def make_illinois_search_request(file_number, cookies, headers):
    """Make the Illinois business entity search request using extracted cookies and headers"""
    
    url = "https://apps.ilsos.gov/businessentitysearch/businessentitysearch"
    
    # Use extracted headers, but ensure content-type and priority are set for form submission
    headers = headers.copy()  # Don't modify the original
    headers.update({
        "content-type": "application/x-www-form-urlencoded",
        "priority": "u=0, i",
        "referer": "https://apps.ilsos.gov/businessentitysearch/businessentitysearch"
    })
    
    print(f"[{file_number}] Using extracted headers with {len(headers)} entries")
    
    # Form data for the search
    data = {
        "command": "entitySearch",
        "method": "search", 
        "searchMethod": "f",
        "searchValue": file_number,
        "maLastName": "",
        "maFirstName": "",
        "maMiddleIni": "",
        "maBusinessName": "",
        "btnSearch": "Submit"
    }
    
    # Create session with extracted cookies
    session = requests.Session()
    session.cookies.update(cookies)
    
    # Make the POST request with timeout
    try:
        print(f"[{file_number}] Making search request...")
        response = session.post(url, headers=headers, data=data, timeout=30)
        print(f"[{file_number}] Search request completed with status: {response.status_code}")
        return response
    except requests.exceptions.Timeout:
        print(f"[{file_number}] Search request timed out")
        raise
    except requests.exceptions.RequestException as e:
        print(f"[{file_number}] Search request failed: {str(e)}")
        raise

def make_illinois_detail_request(transaction_id, cookies, headers):
    """Make the Illinois business detail request using transaction ID, cookies and headers"""
    
    url = "https://apps.ilsos.gov/businessentitysearch/businessentitysearch"
    
    # Use extracted headers, but ensure content-type and priority are set for form submission
    headers = headers.copy()  # Don't modify the original
    headers.update({
        "content-type": "application/x-www-form-urlencoded",
        "priority": "u=0, i",
        "referer": "https://apps.ilsos.gov/businessentitysearch/businessentitysearch"
    })
    
    print(f"[Transaction {transaction_id}] Using extracted headers with {len(headers)} entries")
    
    # Form data for the detail request
    data = {
        "command": "entitySearch",
        "method": "getDetails",
        "transId": transaction_id,
        "resultspage": "",
        "searchValue": "",
        "sortTable_length": "100"
    }
    
    # Create session with extracted cookies
    session = requests.Session()
    session.cookies.update(cookies)
    
    # Make the POST request with timeout
    try:
        print(f"[Transaction {transaction_id}] Making detail request...")
        response = session.post(url, headers=headers, data=data, timeout=30)
        print(f"[Transaction {transaction_id}] Detail request completed with status: {response.status_code}")
        return response
    except requests.exceptions.Timeout:
        print(f"[Transaction {transaction_id}] Detail request timed out")
        raise
    except requests.exceptions.RequestException as e:
        print(f"[Transaction {transaction_id}] Detail request failed: {str(e)}")
        raise

def parse_managers_table(html_content):
    """Parse managers information from the sortManagers table"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find the managers table - try multiple selectors
    managers_table = None
    
    # First try the aria-describedby selector (original approach)
    managers_table = soup.find('table', attrs={'aria-describedby': 'sortManagers_info'})
    
    # If not found, try id selector
    if not managers_table:
        managers_table = soup.find('table', id='sortManagers')
    
    # If still not found, try class-based approach
    if not managers_table:
        # Look for table inside managers tab
        managers_div = soup.find('div', id='managers')
        if managers_div:
            managers_table = managers_div.find('table')
    
    if not managers_table:
        print("No managers table found with any selector")
        
        # Debug: show all tables for troubleshooting
        all_tables = soup.find_all('table')
        print(f"Found {len(all_tables)} total tables on the page")
        
        for i, table in enumerate(all_tables):
            table_text = table.get_text().lower()
            if 'manager' in table_text:
                print(f"Table {i+1} contains 'manager' text")
                print(f"Table {i+1} attributes: {table.attrs}")
        
        return []
    
    print(f"Found managers table with attributes: {managers_table.attrs}")
    managers = []
    
    # Find all rows in the tbody
    tbody = managers_table.find('tbody')
    if tbody:
        rows = tbody.find_all('tr')
        print(f"Found {len(rows)} manager rows")
        
        for row in rows:
            tds = row.find_all('td')
            if len(tds) >= 2:
                # First td is the manager name
                manager_name = tds[0].get_text(strip=True)
                
                # Second td is the address (may contain <br> tags)
                address_td = tds[1]
                # Replace <br> tags with newlines before getting text
                for br in address_td.find_all('br'):
                    br.replace_with('\n')
                
                address = address_td.get_text(strip=True)
                # Clean up address (normalize whitespace but preserve line breaks)
                address = re.sub(r'[ \t]+', ' ', address)  # Replace multiple spaces/tabs with single space
                address = re.sub(r'\n\s*\n', '\n', address)  # Remove empty lines
                address = address.strip()
                
                if manager_name and address:
                    managers.append({
                        "name": manager_name,
                        "address": address
                    })
                    print(f"Added manager: {manager_name}")
    else:
        print("No tbody found in managers table")
    
    return managers

def parse_business_details(html_content):
    """Parse business details from HTML using the display-details pattern"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find the display-details div
    details_div = soup.find('div', class_='display-details')
    if not details_div:
        print("No display-details div found")
        return {}
    
    business_data = {}
    
    # Find all rows within the display-details div
    rows = details_div.find_all('div', class_='row')
    
    for row in rows:
        # Find all columns in this row
        cols = row.find_all('div', class_=re.compile(r'col-'))
        
        if len(cols) >= 2:
            # Process pairs of columns (key-value)
            for i in range(0, len(cols), 2):
                if i + 1 < len(cols):
                    key_col = cols[i]
                    value_col = cols[i + 1]
                    
                    # Extract key (look for <b> tag)
                    key_element = key_col.find('b')
                    if key_element:
                        key = key_element.get_text(strip=True)
                        # Clean up key (remove extra whitespace, line breaks)
                        key = re.sub(r'\s+', ' ', key).strip()
                        
                        # Extract value (get all text, preserve <br> as newlines)
                        # Replace <br> tags with newlines before getting text
                        for br in value_col.find_all('br'):
                            br.replace_with('\n')
                        
                        value = value_col.get_text(strip=True)
                        # Clean up value (normalize whitespace but preserve meaningful line breaks)
                        value = re.sub(r'[ \t]+', ' ', value)  # Replace multiple spaces/tabs with single space
                        value = re.sub(r'\n\s*\n', '\n', value)  # Remove empty lines
                        value = value.strip()
                        
                        if key and value:
                            business_data[key] = value
    
    # Also extract managers information
    managers = parse_managers_table(html_content)
    if managers:
        business_data["managers"] = managers
    
    return business_data

def parse_td_ids(html_content):
    """Parse HTML to find all td elements with id attributes"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find all td elements with id attributes
    td_elements = soup.find_all('td', id=True)
    
    td_ids = []
    for td in td_elements:
        td_id = td.get('id')
        if td_id:
            td_ids.append(td_id)
    
    return td_ids

def get_captcha_solved_cookies_and_headers(file_number):
    """Get cookies and headers by solving captcha once using the provided file number"""
    with SB(uc=True, locale="en") as sb:
        url = "https://apps.ilsos.gov/businessentitysearch/"
        sb.activate_cdp_mode(url, tzone="America/Chicago")
        sb.sleep(3)

        try:
            print("Checking for search input on Illinois page...")
            sb.wait_for_element_present('input[type="text"]', timeout=10)
            print("Search input found on Illinois page!")
            
            # Take screenshot of initial page
            save_screenshot(sb, file_number, "captcha", "initial_page")
            
            sb.sleep(2)
            
            # Click on the file number input field
            print("Clicking on file number input field...")
            sb.click('input[id="fileNumber"]')
            
            # Use the provided file number to trigger captcha
            print(f"Typing file number: {file_number}")
            sb.type('input[name="searchValue"]', file_number)
            
            # Click the submit button
            print("Clicking submit button...")
            sb.click('input[type="submit"]')
            
            sb.sleep(3)
            print("Form submitted successfully!")
            
            # Take screenshot after form submission
            save_screenshot(sb, file_number, "captcha", "after_submit")
            
            # Now check if we're redirected to captcha page
            print("Checking for captcha iframe...")
            try:
                print("Waiting for captcha iframe to be present...")
                sb.wait_for_element_present('iframe[title="Challenge Content"]', timeout=10)
                print("Captcha iframe found")
                
                # Take screenshot when captcha is detected
                save_screenshot(sb, file_number, "captcha", "captcha_detected")

                # Extract sitekey from the iframe's data-key attribute
                sitekey = sb.get_attribute('iframe[title="Challenge Content"]', 'data-key')
                print(f"Found sitekey: {sitekey}")

                if sitekey:
                    # Get current page URL for the captcha API
                    current_url = sb.get_current_url()
                    
                    # Solve the reCAPTCHA
                    print("Solving reCAPTCHA...")
                    token = solve_recaptcha_v2(sitekey, current_url)
                    
                    print("Setting reCAPTCHA token...")
                    
                    try:
                        # Switch to the Challenge Content iframe
                        sb.switch_to_frame('iframe[title="Challenge Content"]')
                        print("Switched to Challenge Content iframe")
                        
                        # Find the g-recaptcha-response textarea and make it visible
                        js_script = f'''
                            var textarea = document.getElementById("g-recaptcha-response");
                            if (textarea) {{
                                var currentStyle = textarea.getAttribute("style");
                                if (currentStyle) {{
                                    var newStyle = currentStyle.replace(/display:\\s*none;?/gi, "");
                                    textarea.setAttribute("style", newStyle);
                                    console.log("Removed display:none from textarea style");
                                }}
                                
                                textarea.value = "{token}";
                                textarea.innerHTML = "{token}";
                                console.log("Token set in textarea");
                                
                                if (typeof verifyAkReCaptcha === 'function') {{
                                    console.log("Calling verifyAkReCaptcha with token...");
                                    verifyAkReCaptcha("{token}");
                                    console.log("verifyAkReCaptcha function called successfully");
                                }}
                            }}
                        '''
                        sb.execute_script(js_script)
                        print("Textarea visibility updated")
                        
                        # Switch back to main content
                        sb.switch_to_default_content()
                        print("Switched back to main content")
                        
                    except Exception as e:
                        print(f"Error making textarea visible: {e}")
                    
                    # Wait for redirection
                    sb.sleep(5)
                    print("Waiting for page redirection...")
                    
                    # Take screenshot after captcha solution
                    save_screenshot(sb, file_number, "captcha", "after_solution")
                    
                    # Extract cookies and headers after redirect
                    print("Extracting cookies and headers from browser...")
                    cookies = {}
                    browser_cookies = sb.get_cookies()
                    for cookie in browser_cookies:
                        cookies[cookie['name']] = cookie['value']
                    
                    # Extract headers using JavaScript
                    headers_script = """
                    return {
                        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                        'accept-language': navigator.language || 'en',
                        'cache-control': 'max-age=0',
                        'content-type': 'application/x-www-form-urlencoded',
                        'origin': window.location.origin,
                        'referer': window.location.href,
                        'sec-ch-ua': navigator.userAgentData ? navigator.userAgentData.brands.map(b => `"${b.brand}";v="${b.version}"`).join(', ') : '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
                        'sec-ch-ua-mobile': navigator.userAgentData ? (navigator.userAgentData.mobile ? '?1' : '?0') : '?0',
                        'sec-ch-ua-platform': navigator.userAgentData ? `"${navigator.userAgentData.platform}"` : '"Windows"',
                        'sec-fetch-dest': 'document',
                        'sec-fetch-mode': 'navigate',
                        'sec-fetch-site': 'same-origin',
                        'sec-fetch-user': '?1',
                        'upgrade-insecure-requests': '1',
                        'user-agent': navigator.userAgent
                    };
                    """
                    
                    headers = sb.execute_script(headers_script)
                    
                    print(f"Extracted {len(cookies)} cookies and {len(headers)} headers")
                    return cookies, headers
                    
                else:
                    print("No sitekey found in iframe")
                    return None, None
                    
            except Exception as captcha_error:
                print(f"No captcha found or captcha error: {captcha_error}")
                # Take screenshot on captcha error for debugging
                save_screenshot(sb, file_number, "captcha", "error")
                return None, None
            
        except Exception as e:
            print(f"Error during captcha solving process: {e}")
            # Take screenshot on general error for debugging
            save_screenshot(sb, file_number, "captcha", "general_error")
            return None, None

def scrape_illinois_business(file_number):
    """Main function to scrape a single Illinois business by file number"""
    print(f"Starting Illinois scraper for file number: {file_number}")
    
    # Step 1: Solve captcha and get cookies
    print("\n" + "="*60)
    print("STEP 1: Solving captcha and extracting cookies...")
    print("="*60)
    
    cookies, headers = get_captcha_solved_cookies_and_headers(file_number)
    
    if not cookies or not headers:
        print("❌ Failed to get cookies and headers from captcha solving")
        return {
            "file_number": file_number,
            "status": "error",
            "error": "Failed to solve captcha and extract cookies/headers"
        }
    
    print("✅ Cookies and headers extracted successfully!")
    
    # Step 2: Make search request
    print("\n" + "="*60)
    print("STEP 2: Making search request...")
    print("="*60)
    
    try:
        response = make_illinois_search_request(file_number, cookies, headers)
    except requests.exceptions.Timeout:
        return {
            "file_number": file_number,
            "status": "error",
            "error": "Search request timed out after 30 seconds"
        }
    except requests.exceptions.RequestException as e:
        return {
            "file_number": file_number,
            "status": "error",
            "error": f"Search request failed: {str(e)}"
        }
    
    if response.status_code != 200:
        save_failed_response(file_number, response, "search_request")
        return {
            "file_number": file_number,
            "status": "error",
            "error": f"Search request failed with status: {response.status_code}"
        }
    
    print(f"✅ Search request successful!")
    
    # Step 3: Parse transaction ID
    print("\n" + "="*60)
    print("STEP 3: Parsing transaction ID...")
    print("="*60)
    
    td_ids = parse_td_ids(response.text)
    
    if not td_ids:
        save_failed_response(file_number, response, "search_parsing")
        return {
            "file_number": file_number,
            "status": "error",
            "error": "No transaction IDs found in search results"
        }
    
    transaction_id = td_ids[0]  # Use the first ID found
    print(f"✅ Found transaction ID: {transaction_id}")
    
    # Step 4: Get business details
    print("\n" + "="*60)
    print("STEP 4: Getting business details...")
    print("="*60)
    
    try:
        detail_response = make_illinois_detail_request(transaction_id, cookies, headers)
    except requests.exceptions.Timeout:
        return {
            "file_number": file_number,
            "transaction_id": transaction_id,
            "status": "error",
            "error": "Detail request timed out after 30 seconds"
        }
    except requests.exceptions.RequestException as e:
        return {
            "file_number": file_number,
            "transaction_id": transaction_id,
            "status": "error",
            "error": f"Detail request failed: {str(e)}"
        }
    
    if detail_response.status_code != 200:
        save_failed_response(file_number, detail_response, "detail_request")
        return {
            "file_number": file_number,
            "transaction_id": transaction_id,
            "status": "error",
            "error": f"Detail request failed with status: {detail_response.status_code}"
        }
    
    print(f"✅ Detail request successful!")
    
    # Save successful response for debugging managers issue
    save_successful_response(file_number, detail_response, "detail_success")
    
    # Step 5: Parse business details and managers
    print("\n" + "="*60)
    print("STEP 5: Parsing business details and managers...")
    print("="*60)
    
    business_details = parse_business_details(detail_response.text)
    
    if not business_details:
        save_failed_response(file_number, detail_response, "detail_parsing")
        return {
            "file_number": file_number,
            "transaction_id": transaction_id,
            "status": "error",
            "error": "No business details found in response"
        }
    
    print(f"✅ Successfully parsed business details!")
    if "managers" in business_details:
        print(f"✅ Found {len(business_details['managers'])} managers")
    
    # Step 6: Return results
    print("\n" + "="*60)
    print("FINAL RESULT:")
    print("="*60)
    
    result = {
        "file_number": file_number,
        "transaction_id": transaction_id,
        "status": "success",
        "data": business_details
    }
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return result

def main():
    """Main function - accepts file number as command line argument or uses default"""
    import sys
    
    # Get file number from command line argument or environment variable or use default
    if len(sys.argv) > 1:
        file_number = sys.argv[1]
    else:
        file_number = os.getenv("FILE_NUMBER", "09853537")
    
    request_id = os.getenv("REQUEST_ID", str(uuid.uuid4()))
    
    print(f"Entity Data Processor")
    print(f"File Number: {file_number}")
    print(f"Request ID: {request_id}")
    
    result = scrape_illinois_business(file_number)
    
    # Create comprehensive output with metadata (following California pattern)
    if result.get("status") == "success":
        final_data = {
            'metadata': {
                'total_files_requested': 1,
                'files_processed': 1,
                'files_remaining': 0,
                'request_id': request_id,
                'blocked': False,
                'scrape_timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
                'scraper_type': 'illinois_business_entity'
            },
            'results': {
                file_number: {
                    'success': True,
                    'file_number': result['file_number'],
                    'transaction_id': result.get('transaction_id'),
                    'data': result['data'],
                    'businesses_found': 1 if result['data'] else 0
                }
            }
        }
    else:
        final_data = {
            'metadata': {
                'total_files_requested': 1,
                'files_processed': 0,
                'files_remaining': 1,
                'request_id': request_id,
                'blocked': False,
                'scrape_timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
                'scraper_type': 'illinois_business_entity'
            },
            'results': {
                file_number: {
                    'success': False,
                    'file_number': result['file_number'],
                    'error': result.get('error', 'Unknown error'),
                    'businesses_found': 0
                }
            }
        }
    
    # Save result to JSON file with request ID
    output_filename = f"processed_data_{request_id}.json"
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=2, ensure_ascii=False)
        print(f"✅ Results saved to: {output_filename}")
        
        # Output JSON data to console for GitHub Actions (following California pattern)
        print("\n=== PROCESSED_DATA_JSON_START ===")
        print(json.dumps(final_data, indent=2))
        print("=== PROCESSED_DATA_JSON_END ===")
        
        # Summary
        print(f"\n🎉 PROCESSING COMPLETE!")
        print(f"📊 File Number: {file_number}")
        print(f"✅ Success: {final_data['metadata']['files_processed']}")
        print(f"🏢 Business found: {final_data['results'][file_number].get('businesses_found', 0)}")
        print(f"📄 Output format: JSON")
        
    except Exception as e:
        print(f"❌ Error saving results: {str(e)}")
        sys.exit(1)
    
    return result

if __name__ == "__main__":
    main()
