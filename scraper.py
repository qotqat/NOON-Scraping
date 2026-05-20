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
    
    products = soup.find_all('div', {'data-component-type': 's-search-result'})
    print(f"[DEBUG] Found {len(products)} products on the page.\n")
    
    history = load_history() 
    current_scraped_data = {}
    
    print("--- PRICE DROP ALERTS ---")
    drops_found = False

    for item in products:
        # 1. Extract Title (Broadened search: Just look for any h2 tag)
        title_element = item.find('h2')
        if not title_element: 
            print("[DEBUG] Skipped an item: Could not find a Title (h2 tag missing).")
            continue
        title = title_element.text.strip()
        
        # Extract Link
        link_element = title_element.find('a')
        product_link = "No Link"
        if link_element and link_element.has_attr('href'):
            href = link_element['href']
            # Convert relative Amazon links if needed
            if href.startswith('/'):
                product_link = "https://www.noon.com/egypt-ar" + href
            else:
                product_link = href
        
        # 2. Extract Price
        price_whole = item.find('span', class_='a-price-whole')
        price_fraction = item.find('span', class_='a-price-fraction')
        
        if price_whole and price_fraction:
            # We found both! Save it.
            current_price = float(f"{price_whole.text.replace(',', '').replace('.', '')}.{price_fraction.text}")
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