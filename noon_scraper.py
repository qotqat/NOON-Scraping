import os
import json
import requests
from bs4 import BeautifulSoup
import csv
from datetime import datetime
import re

API_KEY = os.getenv('SCRAPER_API_KEY')
TARGET_URL = "https://www.noon.com/egypt-en/electronics-and-mobiles/"
HISTORY_FILE = "noon_price_history.json"
CSV_FILE = "noon_price_drops.csv"

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
            # Header updated to reflect a standard Product Link
            writer.writerow(['Date Detected', 'Product Name', 'Old Price (EGP)', 'New Price (EGP)', 'Drop Amount (EGP)', 'Product Link'])

def scrape_noon():
    if not API_KEY:
        print("Error: API Key not found!")
        return

    print("Fetching current prices from Noon Egypt...")
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
    
    product_links = soup.find_all('a', href=lambda href: href and '/p/' in href)
    unique_products = {link['href']: link for link in product_links}.values()
    print(f"[DEBUG] Found {len(unique_products)} unique products on the page.\n")
    
    history = load_history() 
    ensure_csv_exists()
    current_scraped_data = {}
    
    print("--- NOON PRICE DROP ALERTS ---")
    drops_found = False

    for item in unique_products:
        raw_url = item['href']
        base_url = f"https://www.noon.com{raw_url}" if raw_url.startswith('/') else raw_url

        # --- NEW TITLE EXTRACTION LOGIC ---
        title = ""
        title_el = item.find(attrs={"data-qa": "product-name"})
        if title_el:
            title = title_el.text.strip()
        else:
            img = item.find('img')
            if img and img.get('alt'):
                title = img.get('alt').strip()
        
        # If Noon gives us "placeholder", extract the real name from the URL!
        if not title or title.lower() == "placeholder":
            try:
                # Breaks down the URL and grabs the product name section
                url_parts = raw_url.split('/')
                for part in url_parts:
                    if '-' in part and len(part) > 10:
                        # Converts 'hot-60-pro-dual-sim' to 'Hot 60 Pro Dual Sim'
                        title = part.replace('-', ' ').title() 
                        break
            except:
                pass

        # If it STILL couldn't find a real name, skip it
        if not title or title.lower() == "placeholder":
            continue

        # 3. Extract Price
        # Using separator=" " forces spaces between hidden HTML tags so numbers don't squash together
        item_text = item.get_text(separator=" ").replace(',', '')
        
        # Scans the spaced-out text for the FIRST number next to EGP
        price_match = re.search(r'EGP\s*(\d+\.?\d*)', item_text, re.IGNORECASE)
        
        # Fallback: If "EGP" is missing, grab the very first number that has a decimal
        if not price_match:
            price_match = re.search(r'(\d+\.\d{2})', item_text)
        
        if price_match:
            current_price = float(price_match.group(1))

            # 4. Compare Prices and Save to Excel
            unique_key = base_url 
            current_scraped_data[unique_key] = current_price

            if unique_key in history:
                previous_price = history[unique_key]
                if current_price < previous_price:
                    drops_found = True
                    drop_amount = round(previous_price - current_price, 2)
                    
                    print(f"📉 DROP DETECTED: {title[:50]}...")
                    
                    with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
                        writer.writerow([current_time, title, previous_price, current_price, drop_amount, base_url])
        else:
            print(f"[DEBUG] Skipped item: '{title[:40]}...', no EGP Price found.")

    print(f"\n[DEBUG] Successfully extracted prices for {len(current_scraped_data)} items.")
            
    if not drops_found:
        print("No Noon price drops detected this hour.")

    save_history(current_scraped_data)

if __name__ == "__main__":
    scrape_noon()