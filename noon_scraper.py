import os
import json
import requests
from bs4 import BeautifulSoup
import csv
from datetime import datetime
import re
import time

API_KEY = os.getenv('SCRAPER_API_KEY')

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
            # Added the new "Offer Status" column
            writer.writerow(['Date Detected', 'Product Name', 'Old Price (EGP)', 'New Price (EGP)', 'Drop Amount (EGP)', 'Product Link', 'Offer Status'])

def scrape_noon():
    if not API_KEY:
        print("Error: API Key not found!")
        return

    MAX_PAGES = 3 # Adjust this to scrape more pages

    for category_name, paths in CATEGORIES.items():
        print(f"\n========== SCRAPING: {category_name.upper()} ==========")
        
        all_category_data = {} 

        for page in range(1, MAX_PAGES + 1):
            base_url = paths['url']
            separator = '&' if '?' in base_url else '?'
            page_url = f"{base_url}{separator}page={page}"
            
            print(f"\n--- Scraping Page {page} ---")
            
            payload = {
                'api_key': API_KEY, 
                'url': page_url
            }
            
            max_retries = 3
            page_successful = False
            products_found = False
            
            for attempt in range(max_retries):
                try:
                    print(f"Attempt {attempt + 1} of {max_retries}...")
                    response = requests.get('http://api.scraperapi.com', params=payload, timeout=120)
                    
                    if response.status_code == 200:
                        products_found = extract_page_data(response.text, all_category_data)
                        page_successful = True
                        
                        if not products_found:
                            print(f"Page {page} is empty. Reached the end of the category.")
                            break 
                            
                        break 
                    else:
                        print(f"Failed to fetch page {page}. Status code: {response.status_code}")
                        if attempt < max_retries - 1:
                            time.sleep(10)
                            
                except Exception as e:
                    print(f"An error occurred: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(10)
            
            if page_successful and not products_found:
                break
            
            time.sleep(2)

        process_and_save_category(all_category_data, paths['history_file'], paths['csv_file'])


def extract_page_data(html_content, all_data_dict):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    product_links = soup.find_all('a', href=lambda href: href and '/p/' in href)
    unique_products = {link['href']: link for link in product_links}.values()
    print(f"[DEBUG] Found {len(unique_products)} total product links on this page.")
    
    if len(unique_products) == 0:
        return False 

    items_added = 0

    for item in unique_products:
        # --- NOON EXPRESS FILTER ---
        item_full_text = re.sub(r'\s+', ' ', item.get_text(separator=" ").lower())
        is_express = False
        
        if "noon express" in item_full_text:
            is_express = True
            
        for img in item.find_all('img'):
            alt_text = img.get('alt', '').lower()
            if 'noon express' in alt_text or 'noon-express' in alt_text:
                is_express = True
                break

        if not is_express:
            continue 

        # --- URL & TITLE EXTRACTION ---
        raw_url = item['href']
        base_url = f"https://www.noon.com{raw_url}" if raw_url.startswith('/') else raw_url

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

        # --- PRICE & OFFER EXTRACTION ---
        item_text_for_price = item.get_text(separator=" ").replace(',', '')
        
        # Look for multiple prices in the text (Current Price and Crossed-out Old Price)
        prices = re.findall(r'EGP\s*(\d+\.?\d*)', item_text_for_price, re.IGNORECASE)
        
        if not prices:
            prices = re.findall(r'(\d+\.\d{2})', item_text_for_price)
        
        if prices:
            current_price = float(prices[0])
            original_crossed_out_price = current_price
            has_offer = False
            
            # If Noon provides a second price, it is an active Offer
            if len(prices) > 1:
                possible_old = float(prices[1])
                if possible_old > current_price:
                    original_crossed_out_price = possible_old
                    has_offer = True

            unique_key = base_url 
            
            # Save all the new offer data to the master dictionary
            all_data_dict[unique_key] = {
                'price': current_price,
                'title': title,
                'has_offer': has_offer,
                'original_crossed_out_price': original_crossed_out_price
            }
            items_added += 1

    print(f"[DEBUG] Successfully extracted {items_added} 'Express' items from this page.")
    return True


def process_and_save_category(all_category_data, history_file, csv_file):
    history = load_history(history_file) 
    ensure_csv_exists(csv_file)
    
    drops_found = False
    new_history = {}

    print(f"\n--- Analyzing {len(all_category_data)} total items across all pages ---")

    for unique_key, data in all_category_data.items():
        current_price = data['price']
        title = data['title']
        has_offer = data['has_offer']
        noon_original_price = data['original_crossed_out_price']
        
        new_history[unique_key] = current_price

        # Check for historical drops (the old way)
        is_history_drop = False
        previous_history_price = current_price
        if unique_key in history:
            if current_price < history[unique_key]:
                is_history_drop = True
                previous_history_price = history[unique_key]

        # Log to CSV if it has a Noon Offer OR if it dropped in our history
        if has_offer or is_history_drop:
            drops_found = True
            
            # Decide what numbers to display based on why it triggered
            if has_offer:
                display_old_price = noon_original_price
                offer_tag = "🚨 NOON OFFER"
            else:
                display_old_price = previous_history_price
                offer_tag = "Historical Drop"
                
            drop_amount = round(display_old_price - current_price, 2)
            
            if has_offer:
                print(f"🚨 OFFER DETECTED: {title[:50]}... (Was {display_old_price}, Now {current_price})")
            elif is_history_drop:
                print(f"📉 DROP DETECTED: {title[:50]}... (Dropped from {display_old_price})")
            
            with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                current_time = datetime.now().strftime("%b %d, %Y - %I:%M %p")
                writer.writerow([current_time, title, display_old_price, current_price, drop_amount, unique_key, offer_tag])

    if not drops_found:
        print("No drops or offers detected across all pages this run.")

    save_history(new_history, history_file)


if __name__ == "__main__":
    scrape_noon()
