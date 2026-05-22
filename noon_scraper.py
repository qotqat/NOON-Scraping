import os
import json
import requests
from bs4 import BeautifulSoup
import csv
from datetime import datetime
import re
import time

API_KEY = os.getenv('SCRAPER_API_KEY')

# Dictionary containing our target categories and their dedicated files
CATEGORIES = {
    "electronics": {
        "url": "https://www.noon.com/egypt-en/electronics-and-mobiles/",
        "history_file": "noon_electronics_history.json",
        "csv_file": "noon_electronics_drops.csv"
    },
    "mobiles": {
        "url": "https://www.noon.com/egypt-en/electronics-and-mobiles/mobiles-and-accessories/mobiles-20905/",
        "history_file": "noon_mobiles_history.json",
        "csv_file": "noon_mobiles_drops.csv"
    }
}

def load_history(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            return json.load(file)
    return {}

def save_history(history, filename):
    with open(filename, 'w') as file:
        json.dump(history, file, indent=4)

def ensure_csv_exists(filename):
    if not os.path.exists(filename):
        with open(filename, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Date Detected', 'Product Name', 'Old Price (EGP)', 'New Price (EGP)', 'Drop Amount (EGP)', 'Product Link'])

def scrape_noon():
    if not API_KEY:
        print("Error: API Key not found!")
        return

    # Loop through each category one by one
    for category_name, paths in CATEGORIES.items():
        print(f"\n========== SCRAPING: {category_name.upper()} ==========")
        
        payload = {
            'api_key': API_KEY, 
            'url': paths['url'],
            'render': 'true'
        }
        
        # --- THE RETRY SYSTEM ---
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"Attempt {attempt + 1} of {max_retries}...")
                response = requests.get('http://api.scraperapi.com', params=payload, timeout=120)
                
                if response.status_code == 200:
                    process_prices(response.text, paths['history_file'], paths['csv_file'])
                    break  # Success! Break out of the retry loop and move to the next category
                else:
                    print(f"Failed to fetch {category_name}. Status code: {response.status_code}")
                    if attempt < max_retries - 1:
                        print("Waiting 10 seconds before trying again...")
                        time.sleep(10)
                        
            except Exception as e:
                print(f"An error occurred on {category_name}: {e}")
                if attempt < max_retries - 1:
                    print("Waiting 10 seconds before trying again...")
                    time.sleep(10)

def process_prices(html_content, history_file, csv_file):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    product_links = soup.find_all('a', href=lambda href: href and '/p/' in href)
    unique_products = {link['href']: link for link in product_links}.values()
    print(f"[DEBUG] Found {len(unique_products)} total products on the page.\n")
    
    history = load_history(history_file) 
    ensure_csv_exists(csv_file)
    current_scraped_data = {}
    
    drops_found = False

    for item in unique_products:
        # --- SELLER FILTER ("Sold by noon" Check) ---
        item_full_text = item.get_text(separator=" ").lower()
        is_noon = False
        
        # Check text
        if "sold by noon" in item_full_text or "noon express" in item_full_text:
            is_noon = True
            
        # Check image alt tags just in case
        for img in item.find_all('img'):
            alt_text = img.get('alt', '').lower()
            if 'sold by noon' in alt_text or 'noon-express' in alt_text or 'noon express' in alt_text:
                is_noon = True
                break

        # If it is a 3rd party seller, quietly skip it
        if not is_noon:
            continue 

        # --- URL EXTRACTION ---
        raw_url = item['href']
        base_url = f"https://www.noon.com{raw_url}" if raw_url.startswith('/') else raw_url

        # --- TITLE EXTRACTION ---
        title = ""
        title_el = item.find(attrs={"data-qa": "product-name"})
        if title_el:
            title = title_el.text.strip()
        else:
            img = item.find('img')
            if img and img.get('alt'):
                title = img.get('alt').strip()
        
        if not title or title.lower() == "placeholder":
            try:
                url_parts = raw_url.split('/')
                for part in url_parts:
                    if '-' in part and len(part) > 10:
                        title = part.replace('-', ' ').title() 
                        break
            except:
                pass

        if not title or title.lower() == "placeholder":
            continue

        # --- PRICE EXTRACTION ---
        item_text = item.get_text(separator=" ").replace(',', '')
        price_match = re.search(r'EGP\s*(\d+\.?\d*)', item_text, re.IGNORECASE)
        
        if not price_match:
            price_match = re.search(r'(\d+\.\d{2})', item_text)
        
        if price_match:
            current_price = float(price_match.group(1))
            unique_key = base_url 
            current_scraped_data[unique_key] = current_price

            if unique_key in history:
                previous_price = history[unique_key]
                if current_price < previous_price:
                    drops_found = True
                    drop_amount = round(previous_price - current_price, 2)
                    
                    print(f"📉 DROP DETECTED: {title[:50]}...")
                    
                    with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        # Changed the date format to be explicit text so Google Sheets renders it properly
                        current_time = datetime.now().strftime("%b %d, %Y - %I:%M %p")
                        writer.writerow([current_time, title, previous_price, current_price, drop_amount, base_url])

    print(f"\n[DEBUG] Successfully extracted {len(current_scraped_data)} 'Sold by Noon' items.")
            
    if not drops_found:
        print("No drops detected this hour.")

    save_history(current_scraped_data, history_file)

if __name__ == "__main__":
    scrape_noon()
