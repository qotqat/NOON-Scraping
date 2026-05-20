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
    # Swapped render: true to false, bypasses the 500 error on limited ScraperAPI plans 
    payload = {'api_key': API_KEY, 'url': TARGET_URL, 'country_code': 'eg'}
    
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
    
    import json
    history = load_history() 
    current_scraped_data = {}
    products_found = 0

    print("--- PRICE DROP ALERTS ---")
    drops_found = False

    # Noon uses Next.js. Products are embedded in the __NEXT_DATA__ JSON script tag
    script_tag = soup.find('script', id='__NEXT_DATA__')
    if script_tag:
        try:
            data = json.loads(script_tag.string)
            # Find the catalog hits inside the deeply nested NextJS structure
            hits = data.get('props', {}).get('pageProps', {}).get('catalog', {}).get('hits', [])
            
            for item in hits:
                title = item.get('name', 'Unknown')
                product_link = "https://www.noon.com/egypt-ar/" + item.get('url', '')
                current_price = item.get('price', 0)
                
                if current_price and title != 'Unknown':
                    products_found += 1
                    current_scraped_data[title] = {"price": float(current_price), "link": product_link}
        except Exception as e:
            print(f"[DEBUG] Error parsing __NEXT_DATA__: {e}")
    
    # Fallback to HTML parsing if JSON hits are empty (eg API blocks the tag)
    if products_found == 0:
        all_links = soup.find_all('a', href=True)
        products_html = []
        for link in all_links:
            title_elem = link.find(attrs={'data-qa': lambda v: v and ('product-name' in v or 'product-box-name' in v)})
            if title_elem:
                products_html.append((link, title_elem))
                
        for item, title_element in products_html:
            title = title_element.get('title', '').strip() or title_element.text.strip()
            href = item['href']
            product_link = "https://www.noon.com" + href if href.startswith('/') else href
            
            price_container = item.find(attrs={'data-qa': 'product-box-price'}) or item.find(class_=lambda x: x and 'price' in x.lower() if isinstance(x, str) else False)
            price_amount = price_container.find('strong') or price_container.find('span', class_='amount') if price_container else None
            
            if price_amount:
                try:
                    current_price = float(price_amount.text.strip().replace(',', ''))
                    current_scraped_data[title] = {"price": current_price, "link": product_link}
                    products_found += 1
                except ValueError:
                    continue

    print(f"[DEBUG] Found {products_found} products on the page.\n")

    for title, info in current_scraped_data.items():
        current_price = info["price"]
        # 3. Compare Prices
        if title in history:
            previous_data = history[title]
            previous_price = previous_data["price"] if isinstance(previous_data, dict) else previous_data
            if current_price < previous_price:
                drops_found = True
                drop_amount = round(previous_price - current_price, 2)
                print(f"📉 DROP DETECTED: {title[:60]}...")
                print(f"   Old Price: ${previous_price} | New Price: ${current_price} | You save: ${drop_amount}\n")

    # --- NEW DEBUG SUMMARY ---
    print(f"\n[DEBUG] Successfully extracted prices for {len(current_scraped_data)} items.")
            
    if not drops_found:
        if not history:
            print("First run completed. Baseline prices recorded for next hour.")
        else:
            print("No price drops detected this hour.")

    # Save the new prices to history
    save_history(current_scraped_data)

if __name__ == "__main__":
    scrape_amazon()