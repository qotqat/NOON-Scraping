import os
import json
import requests
from bs4 import BeautifulSoup
import csv
from datetime import datetime
import re

# Fetch API Key from GitHub Secrets (Same key you used for Amazon!)
API_KEY = os.getenv('SCRAPER_API_KEY')

# Noon Egypt Electronics Category
TARGET_URL = "https://www.noon.com/egypt-en/electronics-and-mobiles/"

# We use separate files so it doesn't overwrite your Amazon data
HISTORY_FILE = "noon_price_history.json"
CSV_FILE = "noon_price_drops.csv"

# REPLACE THIS with your specific Noon Affiliate tracking parameters
AFFILIATE_PARAMS = "utm_source=affiliate_network&utm_medium=your_affiliate_id" 

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as file:
            return json.load(file)
    return {}

def save_history(history):
    with open(HISTORY_FILE, 'w') as file:
        json.dump(history, file, indent=4)

def ensure_csv_exists():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Date Detected', 'Product Name', 'Old Price (EGP)', 'New Price (EGP)', 'Drop Amount (EGP)', 'Affiliate Link'])

def scrape_noon():
    if not API_KEY:
        print("Error: API Key not found!")
        return

    print("Fetching current prices from Noon Egypt...")
    # Using ScraperAPI. Note: we remove country_code to let the API route naturally
    payload = {'api_key': API_KEY, 'url': TARGET_URL}
    
    try:
        response = requests.get('http://api.scraperapi.com', params=payload, timeout=60)
        if response.status_code == 200:
            process_prices(response.text)
        else:
            print(f"Failed to fetch. Status code: {response.status_code}")
    except Exception as e:
        print(f"An error occurred: {e}")

def process_prices(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    page_title = soup.title.text.strip() if soup.title else "No Title"
    print(f"\n[DEBUG] Page Title Received: {page_title}")
    
    # Noon product links almost always contain '/p/' in the URL
    product_links = soup.find_all('a', href=lambda href: href and '/p/' in href)
    
    # Deduplicate (Noon sometimes has overlapping invisible links for the same item)
    unique_products = {link['href']: link for link in product_links}.values()
    print(f"[DEBUG] Found {len(unique_products)} unique products on the page.\n")
    
    history = load_history() 
    ensure_csv_exists()
    current_scraped_data = {}
    
    print("--- NOON PRICE DROP ALERTS ---")
    drops_found = False

    for item in unique_products:
        # 1. Extract URL and Build Affiliate Link
        raw_url = item['href']
        base_url = f"https://www.noon.com{raw_url}" if raw_url.startswith('/') else raw_url
        
        # Safely append affiliate parameters
        affiliate_url = f"{base_url}&{AFFILIATE_PARAMS}" if "?" in base_url else f"{base_url}?{AFFILIATE_PARAMS}"

        # 2. Extract Title
        title = ""
        # Noon typically uses this data attribute for product names
        title_el = item.find(attrs={"data-qa": "product-name"})
        if title_el:
            title = title_el.text.strip()
        else:
            # Fallback: Grab the alt text from the product image
            img = item.find('img')
            if img and img.get('alt'):
                title = img.get('alt').strip()
        
        if not title:
            continue # Skip items where we can't figure out the name

        # 3. Extract Price (Robust Regex Method)
        # Remove commas first (so "1,250" becomes "1250")
        item_text = item.text.replace(',', '')
        
        # Search for "EGP" followed by any spacing, then numbers
        price_match = re.search(r'EGP\s*(\d+\.?\d*)', item_text)
        
        if price_match:
            current_price = float(price_match.group(1))
            current_scraped_data[title] = current_price

            # 4. Compare Prices and Save to Excel
            if title in history:
                previous_price = history[title]
                if current_price < previous_price:
                    drops_found = True
                    drop_amount = round(previous_price - current_price, 2)
                    
                    print(f"📉 DROP DETECTED: {title[:50]}...")
                    
                    # Log to CSV
                    with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
                        writer.writerow([current_time, title, previous_price, current_price, drop_amount, affiliate_url])
        else:
            print(f"[DEBUG] Skipped item: Found title '{title[:40]}...', but could not find the EGP Price.")

    print(f"\n[DEBUG] Successfully extracted prices for {len(current_scraped_data)} out of {len(unique_products)} items.")
            
    if not drops_found:
        print("No Noon price drops detected this hour.")

    save_history(current_scraped_data)

if __name__ == "__main__":
    scrape_noon()