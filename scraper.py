import os
import time
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotInteractableException
import pandas as pd
import re
import json
from datetime import datetime # Import datetime for timestamp

# --- AI Integration Imports ---
from dotenv import load_dotenv
import google.generativeai as genai

# Load API key for Gemini
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# --- Configuration ---
target_url = "https://www.tradingview.com/markets/stocks-kenya/market-movers-all-stocks/"
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
# Ensure you replace this with the actual path to your chromedriver.exe
chrome_driver_path = "C:\\Users\\USER\\Desktop\\Software\\chromedriver-win64\\chromedriver.exe"

options = Options()
options.add_argument(f"user-agent={user_agent}")
options.add_argument("--headless") # Run in headless mode (no browser UI)
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--log-level=3")

# --- Function to send data to Gemini for final cleaning ---
def send_to_gemini_for_cleaning(data_to_clean):
    """
    Sends a list of stock entries to Gemini for cleaning and returns the cleaned data.
    """
    if not data_to_clean:
        print("No data to send to Gemini.")
        return []

    # Using a clearer prompt with explicit JSON requirement and an example
    prompt = f"""
    You are a data cleaning assistant for stock prices.
    Clean the following list of stock entries. For each entry:
    - Ensure it has a valid stock **name** (company or symbol) and a **numeric price**.
    - Standardize the **price** to a floating-point number (e.g., 1200.00), removing any currency symbols, commas, or extra text.
    - Remove or correct any malformed, missing, or invalid entries.
    - If a name is empty or clearly invalid, discard the entry.
    - If a price cannot be converted to a valid number, discard the entry.
    - IMPORTANT: If the price for "Absa" is "Ksh 92,40", interpret it as 92.40.
    
    Return ONLY a cleaned list of Python dictionaries in JSON format. Do NOT include any other text, markdown formatting (like ```json), or explanations outside the JSON array.

    Example of desired output:
    [
        {{"name": "Safaricom", "price": 1200.00}},
        {{"name": "KCB", "price": 56.75}}
    ]

    Here is the raw data to clean:
    {json.dumps(data_to_clean, indent=2)}
    """

    model = genai.GenerativeModel("gemini-1.5-flash") # Using a fast model
    
    try:
        print("Sending data to Gemini for cleaning...")
        # Add a timeout to prevent hanging indefinitely
        response = model.generate_content(prompt, request_options={"timeout": 120}) # 120 seconds timeout
        
        # Check if any text content was generated
        if not response.text:
            print("Gemini response was empty.")
            return []

        cleaned_text = response.text.strip()
        # print(f"Raw Gemini response text:\n{cleaned_text[:500]}...") # Print first 500 chars for debugging

        # More robust extraction of JSON: Look for the first '[' and last ']'
        # This tries to be resilient if Gemini adds text before or after the JSON.
        json_start = cleaned_text.find('[')
        json_end = cleaned_text.rfind(']')

        if json_start == -1 or json_end == -1:
            print("Could not find a valid JSON array structure in Gemini's response.")
            return []
        
        # Extract the potential JSON string
        json_string_to_parse = cleaned_text[json_start : json_end + 1]

        # Attempt to parse the JSON output
        cleaned_data = json.loads(json_string_to_parse)
        print("Gemini cleaned data successfully.")
        return cleaned_data
    except json.JSONDecodeError as e:
        print(f"JSON decoding error from Gemini response: {e}")
        print(f"Attempted to parse: {json_string_to_parse[:500]}...") # Show what was attempted to parse
        return []
    except Exception as e:
        print(f"Error processing data with Gemini: {e}")
        return []

# --- Main Scraping Function (remains the same) ---
def perform_single_scrape_and_clean():
    print(f"Starting single scrape for {target_url}...")
    browser = None
    all_scraped_data_for_ai = []    

    try:
        service = Service(executable_path=chrome_driver_path)
        browser = webdriver.Chrome(service=service, options=options)
        browser.implicitly_wait(7)
        browser.maximize_window()
        browser.get(target_url)

        try:
            more_button = WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((By.XPATH, '//button[.//span[text()="More"]]'))
            )
            if more_button.is_displayed() and more_button.is_enabled():
                more_button.click()
                time.sleep(2)
        except (NoSuchElementException, TimeoutException):
            print("Info: No 'More' button found or it's not interactable.")

        all_tab_elements = browser.find_elements(By.XPATH, '//div[@id="market-screener-header-columnset-tabs"]/button')
        categories = []
        for tab_element in all_tab_elements:
            try:
                category_name_element = tab_element.find_element(By.CLASS_NAME, 'content-mf1FlhVw')
                category_name = category_name_element.text.strip()
                if category_name and category_name != "More":
                    categories.append(category_name)
            except NoSuchElementException:
                continue

        selected_category = "All Stocks"
        if selected_category not in categories:
            print(f"Warning: '{selected_category}' category not found. Scraping the first available category.")
            if categories:
                selected_category = categories[0]
            else:
                raise Exception("No categories found to scrape.")
        
        try:
            tab_button = WebDriverWait(browser, 10).until(
                EC.element_to_be_clickable((By.XPATH, f'//button[.//span[text()="{selected_category}"]]'))
            )
            browser.execute_script("arguments[0].scrollIntoView(true);", tab_button)
            tab_button.click()
            WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'table-Ngq2xrcG'))
            )
            time.sleep(1.5)
            print(f"Initialized scraper for category: {selected_category}")
        except Exception as e:
            print(f"Could not select initial category {selected_category}: {e}")
            return []

        print(f"\n--- Performing single scrape from {selected_category} ---")
        
        header_elements = browser.find_elements(By.XPATH, '//table[contains(@class, "table-Ngq2xrcG")]/thead/tr/th')
        headers = [h.text.strip() for h in header_elements if h.text.strip()]

        rows = browser.find_elements(By.XPATH, '//table[contains(@class, "table-Ngq2xrcG")]/tbody/tr')

        for row in rows:
            stock_symbol = "N/A"
            company_name = "N/A"
            current_price = "N/A"

            try:
                symbol_link_element = row.find_element(By.XPATH, './/td[1]//a[contains(@class, "tickerName-GrtoTeat")]')
                stock_symbol = symbol_link_element.text.strip()
            except NoSuchElementException:
                try:
                    first_cell_text = row.find_element(By.XPATH, './/td[1]').text.strip()
                    stock_symbol = first_cell_text.split('\n')[0].strip()
                except NoSuchElementException:
                    stock_symbol = "N/A_NoText"
            
            try:
                company_name_element = row.find_element(By.XPATH, './/sup[contains(@class, "tickerDescription-GrtoTeat")]')
                company_name = company_name_element.text.strip()
            except NoSuchElementException:
                pass

            cells = row.find_elements(By.TAG_NAME, 'td')
            if headers and "Price" in headers:
                try:
                    price_index = headers.index("Price")
                    if price_index < len(cells):
                        current_price = cells[price_index].text.strip()
                except ValueError:
                    pass
                except IndexError:
                    pass

            all_scraped_data_for_ai.append({
                "name": company_name if company_name != "N/A" else stock_symbol,
                "price": current_price
            })

        print(f"Scraped {len(all_scraped_data_for_ai)} entries.")
        return all_scraped_data_for_ai

    except Exception as e:
        print(f"An error occurred during scraping: {e}")
        return []
    finally:
        if browser:
            browser.quit()
            print("Browser closed.")

def scrape_and_save_stocks():
    """
    Performs scraping and cleaning, then saves the cleaned data to a JSON file.
    """
    raw_data_for_ai = perform_single_scrape_and_clean()
    
    if raw_data_for_ai:
        cleaned_data = send_to_gemini_for_cleaning(raw_data_for_ai)
        
        if cleaned_data:
            output_filename = "cleaned_stock_prices.json"
            try:
                # --- FIX APPLIED HERE ---
                timestamp = datetime.now().isoformat()
                data_to_save = {
                    "stocks": cleaned_data,
                    "timestamp": timestamp
                }

                with open(output_filename, 'w') as f:
                    json.dump(data_to_save, f, indent=4)
                # --- END FIX ---

                print(f"\nSuccessfully saved cleaned data to {output_filename}")
                return data_to_save # Return the dictionary structure for consistency
            except Exception as e:
                print(f"Error saving cleaned data to JSON: {e}")
                return []
        else:
            print("No cleaned data received from Gemini. JSON file not created.")
            return []
    else:
        print("No raw data scraped, so no cleaning or saving performed.")
        return []

if __name__ == "__main__":
    scrape_and_save_stocks()