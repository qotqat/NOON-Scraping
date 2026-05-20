import os
import json
import requests
import pandas as pd
from bs4 import BeautifulSoup

API_KEY = os.getenv('SCRAPER_API_KEY')
TARGET_URL = "https://www.noon.com/egypt-ar/mobiles/"
HISTORY_FILE = "price_history.json"

def load_history():
    """Loads the previous hour's prices from the JSON file."""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as file:
            return json.load(file)
    return {}

def save_history(history):
    """Saves the current prices to the JSON file."""
    with open(HISTORY_FILE, 'w') as file:
        json.dump(history, file, indent=4)
    export_to_excel(history)

def export_to_excel(history):
    """Exports the history to an Excel file."""
    data = []
    for title, info in history.items():
        if isinstance(info, dict):
            price = info.get("price", "N/A")
            link = info.get("link", "N/A")
        else:
            price = info
            link = "N/A"
        data.append({"Product Title": title, "Price": price, "Link": link})
    
    if data:
        df = pd.DataFrame(data)
        df.to_excel("prices.xlsx", index=False)
        print("Exported data to prices.xlsx")

def scrape_amazon():
    if not API_KEY:
        print("Error: API Key not found!")
        return

    print("Fetching current prices...")
    payload = {'api_key': API_KEY, 'url': TARGET_URL, 'country_code': 'us'}
    
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
    
    # Find all product wrapped in <a> tags that actually contain a product title
    all_links = soup.find_all('a', href=True)
    products = [link for link in all_links if link.find(attrs={'data-qa': 'product-box-name'})]
    
    print(f"[DEBUG] Found {len(products)} products on the page.\n")
    
    history = load_history() 
    current_scraped_data = {}
    
    print("--- PRICE DROP ALERTS ---")
    drops_found = False

    for item in products:
        # 1. Extract Title
        title_element = item.find(attrs={'data-qa': 'product-box-name'})
        title = title_element.get('title', '').strip() or title_element.text.strip()
        
        # Extract Link (The item itself is the link element on Noon)
        href = item['href']
        if href.startswith('/'):
            product_link = "https://www.noon.com" + href
        else:
            product_link = href
        
        # 2. Extract Price
        price_container = item.find(attrs={'data-qa': 'product-box-price'})
        price_amount = price_container.find('strong') if price_container else None
        
        if price_amount:
            # We found the price, clean up formatting (e.g. 7,649)
            current_price = float(price_amount.text.strip().replace(',', ''))
            current_scraped_data[title] = {"price": current_price, "link": product_link}

            # 3. Compare Prices
            if title in history:
                previous_data = history[title]
                previous_price = previous_data["price"] if isinstance(previous_data, dict) else previous_data
                if current_price < previous_price:
                    drops_found = True
                    drop_amount = round(previous_price - current_price, 2)
                    print(f"📉 DROP DETECTED: {title[:60]}...")
                    print(f"   Old Price: ${previous_price} | New Price: ${current_price} | You save: ${drop_amount}\n")
        else:
            print(f"[DEBUG] Skipped item: Found title '{title[:40]}...', but could not find the Price.")

    # --- NEW DEBUG SUMMARY ---
    print(f"\n[DEBUG] Successfully extracted prices for {len(current_scraped_data)} out of {len(products)} items.")
            
    if not drops_found:
        if not history:
            print("First run completed. Baseline prices recorded for next hour.")
        else:
            print("No price drops detected this hour.")

    # Save the new prices to history
    save_history(current_scraped_data)

if __name__ == "__main__":
    scrape_amazon()