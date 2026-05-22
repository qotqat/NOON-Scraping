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

    # SAFETY LIMIT: Adjust this to scrape more pages (Careful with API credit limits!)
    MAX_PAGES = 10 

    # Loop through each category one by one
    for category_name, paths in CATEGORIES.items():
        print(f"\n========== SCRAPING: {category_name.upper()} ==========")
        
        # This dictionary will hold EVERY product across ALL pages for this category
        all_category_data = {} 

        for page in range(1, MAX_PAGES + 1):
            # Construct pagination URL (Adds ?page=1, ?page=2, etc.)
            base_url = paths['url']
            separator = '&' if '?' in base_url else '?'
            page_url = f"{base_url}{separator}page={page}"
            
            print(f"\n--- Scraping Page {page} ---")
            
            payload = {
                'api_key': API_KEY, 
                'url': page_url
                # 'render': 'true' # Left disabled as per your setup
            }
            
            max_retries = 3
            page_successful = False
            products_found = False
            
            for attempt in range(max_retries):
                try:
                    print(f"Attempt {attempt + 1} of {max_retries}...")
                    response = requests.get('http://api.scraperapi.com', params=payload, timeout=120)
                    
                    if response.status_code == 200:
                        # Extract products and add them to our master dictionary
                        products_found = extract_page_data(response.text, all_category_data)
                        page_successful = True
                        
                        if not products_found:
                            print(f"Page {page} is empty. Reached the end of the category.")
                            break # Break the retry loop
                            
                        break # Success! Break the retry loop and move to next page
                    else:
                        print(f"Failed to fetch page {page}. Status code: {response.status_code}")
                        if attempt < max_retries - 1:
                            print("Waiting 10 seconds before trying again...")
                            time.sleep(10)
                            
                except Exception as e:
                    print(f"An error occurred: {e}")
                    if attempt < max_retries - 1:
                        print("Waiting 10 seconds before trying again...")
                        time.sleep(10)
            
            # If we broke out of the retry loop because the page was empty, stop paginating entirely
            if page_successful and not products_found:
                break
            
            # Brief pause between pages to be gentle on the servers
            time.sleep(2)

        # After checking ALL pages for this category, compare and save the massive list
        process_and_save_category(all_category_data, paths['history_file'], paths['csv_file'])


def extract_page_data(html_content, all_data_dict):
    """Parses a single HTML page and appends products to the master dictionary."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    product_links = soup.find_all('a', href=lambda href: href and '/p/' in href)
    unique_products = {link['href']: link for link in product_links}.values()
    print(f"[DEBUG] Found {len(unique_products)} total product links on this page.")
    
    # If the page is empty, return False to stop pagination
    if len(unique_products) == 0:
        return False 

    items_added = 0

    for item in unique_products:
        # --- SELLER FILTER STRICT ("Sold by noon" ONLY) ---
        # We use regex to collapse any weird, giant spaces down to a single space
        item_full_text = re.sub(r'\s+', ' ', item.get_text(separator=" ").lower())
        is_noon = False
        
        # Strictly look ONLY for "sold by noon"
        if "sold by noon" in item_full_text:
            is_noon = True
            
        # Check image alt tags just in case, again ONLY for "sold by noon"
        for img in item.find_all('img'):
            alt_text = img.get('alt', '').lower()
            if 'sold by noon' in alt_text:
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
            
            # Save both the price and the title to the master dictionary
            all_data_dict[unique_key] = {
                'price': current_price,
                'title': title
            }
            items_added += 1

    print(f"[DEBUG] Successfully extracted {items_added} 'Sold by Noon' items from this page.")
    return True # Found products, tell the script to continue to the next page


def process_and_save_category(all_category_data, history_file, csv_file):
    """Compares the massive dictionary of all pages against the JSON memory."""
    history = load_history(history_file) 
    ensure_csv_exists(csv_file)
    
    drops_found = False
    new_history = {}

    print(f"\n--- Analyzing {len(all_category_data)} total items across all pages ---")

    for unique_key, data in all_category_data.items():
        current_price = data['price']
        title = data['title']
        
        # Rebuild the history dictionary with just the prices for the next hour
        new_history[unique_key] = current_price

        if unique_key in history:
            previous_price = history[unique_key]
            if current_price < previous_price:
                drops_found = True
                drop_amount = round(previous_price - current_price, 2)
                
                print(f"📉 DROP DETECTED: {title[:50]}...")
                
                with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    current_time = datetime.now().strftime("%b %d, %Y - %I:%M %p")
                    writer.writerow([current_time, title, previous_price, current_price, drop_amount, unique_key])

    if not drops_found:
        print("No drops detected across all pages this run.")

    # Save the massive new dictionary to the JSON file
    save_history(new_history, history_file)


if __name__ == "__main__":
    scrape_noon()
