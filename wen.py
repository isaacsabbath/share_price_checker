import os
import json
import time
from datetime import datetime, time as dt_time, timedelta
from dotenv import load_dotenv
import africastalking
from db import get_all_subscribers
from scraper import scrape_and_save_stocks

load_dotenv()

# AfricasTalking API configuration
USERNAME = os.getenv("username")
API_KEY = os.getenv("api_key")
SENDER_ID = os.getenv("sender_id")

# Initialize AfricasTalking
try:
    africastalking.initialize(USERNAME, API_KEY)
    sms = africastalking.SMS
    print("AfricasTalking SDK initialized successfully in notification_scheduler.py")
except Exception as e:
    print(f"Error initializing AfricasTalking SDK in notification_scheduler.py: {e}")
    print("Ensure AT_USERNAME and AT_API_KEY are correctly set in your .env file.")
    exit(1)

# Global constants and file paths
STOCKS_JSON_FILE = "cleaned_stock_prices.json"
STATUS_FILE = "scheduler_status.json" # New constant for the status file

# Market Operating Hours (Kenyan Stock Market)
MARKET_OPEN_HOUR = 8  # 8 AM
MARKET_CLOSE_HOUR = 15 # 3 PM (15:00)
MARKET_CLOSE_MINUTE_BUFFER = 5 # Allow for a small buffer, e.g., until 3:05 PM for scraping/notifications
SCRAPE_INTERVAL_MINUTES = 5 # How often to scrape during market hours


# --- FUNCTION DEFINITIONS GO HERE ---

def load_last_notification_status():
    """
    Loads the last notification status and scrape time from a JSON file.
    Returns (last_notification_sent_dict, last_scrape_time_iso_string)
    """
    try:
        with open(STATUS_FILE, 'r') as f:
            data = json.load(f)
            last_notification_sent = data.get("last_notification_sent", {"open": None, "close": None})
            last_scrape_time = data.get("last_scrape_time", None)
            return last_notification_sent, last_scrape_time
    except (FileNotFoundError, json.JSONDecodeError):
        # Return default values if file doesn't exist or is invalid
        print(f"Status file '{STATUS_FILE}' not found or corrupted. Initializing new status.")
        return {"open": None, "close": None}, None

def save_last_notification_status(last_notification_sent_dict, last_scrape_time_iso_string):
    """
    Saves the last notification status and scrape time to a JSON file.
    """
    data = {
        "last_notification_sent": last_notification_sent_dict,
        "last_scrape_time": last_scrape_time_iso_string
    }
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except IOError as e:
        print(f"Error saving status to '{STATUS_FILE}': {e}")


def get_current_stock_prices():
    """
    Loads stock prices from the cleaned_stock_prices.json file.
    Returns (list of stocks, last_modified_timestamp)
    """
    try:
        with open(STOCKS_JSON_FILE, 'r') as f:
            data = json.load(f)
            # Assuming the JSON might have a "stocks" key or be a direct list
            stocks = data.get("stocks", data)
            # Optional: Get file modification time if you want to use it
            # last_mod_timestamp = os.path.getmtime(STOCKS_JSON_FILE)
            return stocks, None # Or return last_mod_timestamp if needed
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Error loading stock prices from {STOCKS_JSON_FILE}. File might be missing or corrupted.")
        return [], None


def send_market_notification(notification_type):
    global last_notification_sent # This needs to be a global variable, initialized in run_scheduler
    # ... (the rest of your send_market_notification function) ...
    current_time = datetime.now()
    today_date_str = current_time.strftime("%Y-%m-%d")

    if notification_type == 'open' and last_notification_sent['open'] == today_date_str:
        print("Market open notification already sent today.")
        return
    if notification_type == 'close' and last_notification_sent['close'] == today_date_str:
        print("Market close notification already sent today.")
        return

    print(f"Sending market {notification_type} notifications...")
    subscribers = get_all_subscribers()
    current_stocks_data, _ = get_current_stock_prices() # Get stocks for notification

    if not current_stocks_data:
        print("No stock data available for notifications. Skipping.")
        return

    # Handle data from scraper if it returns a dict with "stocks" key
    if isinstance(current_stocks_data, dict) and "stocks" in current_stocks_data:
        current_stocks = current_stocks_data["stocks"]
    else:
        current_stocks = current_stocks_data # Assume it's already a list if not dict

    if not current_stocks:
         print("No valid stock data found in JSON for notifications. Skipping.")
         return

    stock_dict = {stock['name'].lower(): stock['price'] for stock in current_stocks if 'name' in stock and 'price' in stock}

    for subscriber in subscribers:
        phone_number = subscriber[0]
        subscribed_stocks_json = subscriber[1]
        market_open_notify = subscriber[2]
        market_close_notify = subscriber[3]

        send_notification = False
        if notification_type == 'open' and market_open_notify == 1:
            send_notification = True
        elif notification_type == 'close' and market_close_notify == 1:
            send_notification = True

        if send_notification:
            subscribed_stocks = json.loads(subscribed_stocks_json)
            if not subscribed_stocks:
                message = f"Market {notification_type} update: No stocks selected for notifications. Dial USSD to select."
            else:
                message_parts = [f"Market {notification_type.capitalize()} Update:"]
                for stock_name in subscribed_stocks:
                    price = stock_dict.get(stock_name.lower())
                    if price is not None:
                        message_parts.append(f"{stock_name}: Ksh {price:.2f}")
                    else:
                        message_parts.append(f"{stock_name}: Price N/A")
                message = "\n".join(message_parts)

            try:
                recipients = [phone_number]
                if SENDER_ID:
                    sms.send(message, recipients, senderId=SENDER_ID)
                else:
                    sms.send(message, recipients)
                print(f"Sent {notification_type} notification to {phone_number} for stocks: {', '.join(subscribed_stocks)}")
                time.sleep(0.1)
            except Exception as e:
                print(f"Error sending SMS to {phone_number}: {e}")

    # Make sure last_scrape_time is accessible or pass it
    # If last_scrape_time is global and set in run_scheduler, this is fine
    # Otherwise, you might need to manage it differently or pass it as an argument
    global last_scrape_time # Declare it global if modified here
    last_notification_sent[notification_type] = today_date_str
    save_last_notification_status(last_notification_sent, last_scrape_time.isoformat() if last_scrape_time else None)
    print(f"Finished sending market {notification_type} notifications.")


def run_scheduler():
    """Main function to run the notification and scraping scheduler."""
    global last_notification_sent, last_scrape_time
    last_notification_sent, last_scrape_time = load_last_notification_status()
    print("Notification and scraping scheduler started. Monitoring market hours...")

    # ... (rest of your run_scheduler logic) ...
    if last_scrape_time:
        try:
            last_scrape_time = datetime.fromisoformat(last_scrape_time)
        except (ValueError, TypeError): # Add TypeError in case last_scrape_time is None
            print("Warning: Invalid last_scrape_time format, resetting.")
            last_scrape_time = datetime.now() - timedelta(minutes=SCRAPE_INTERVAL_MINUTES + 1)
    else:
        last_scrape_time = datetime.now() - timedelta(minutes=SCRAPE_INTERVAL_MINUTES + 1)

    while True:
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        current_weekday = now.weekday() # Monday is 0, Sunday is 6

        is_weekday = 0 <= current_weekday <= 4

        market_open_dt_time = dt_time(MARKET_OPEN_HOUR, 0)
        market_close_dt_time = dt_time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE_BUFFER)

        is_during_market_hours = (dt_time(current_hour, current_minute) >= market_open_dt_time and
                                dt_time(current_hour, current_minute) <= market_close_dt_time)

        # --- Periodic Scraping Logic ---
        if is_weekday and is_during_market_hours:
            if (now - last_scrape_time).total_seconds() >= SCRAPE_INTERVAL_MINUTES * 60:
                print(f"Time to scrape! Last scrape was at {last_scrape_time.strftime('%H:%M:%S')}")
                print("Performing periodic stock scrape...")
                scraped_data_info = scrape_and_save_stocks()
                last_scrape_time = now
                save_last_notification_status(last_notification_sent, last_scrape_time.isoformat())
                print("Periodic scrape complete.")
        else:
            pass

        # --- Market Open/Close Notification Logic ---
        if is_weekday and current_hour == MARKET_OPEN_HOUR and current_minute >= 0 and current_minute < 10:
            send_market_notification('open')

        if is_weekday and current_hour == MARKET_CLOSE_HOUR and current_minute >= 0 and current_minute < 10:
            send_market_notification('close')

        # Reset notification status at midnight for the next day
        if current_hour == 0 and current_minute == 5: # Reset early morning
            today_date_str = now.strftime("%Y-%m-%d")
            # Only reset if the date has changed since the last recorded notification
            if last_notification_sent['open'] != today_date_str:
                last_notification_sent['open'] = None
                last_notification_sent['close'] = None
                last_scrape_time = None # Reset scrape time as well for the new day
                save_last_notification_status(last_notification_sent, None) # Pass None for scrape time
                print("Daily notification and scrape status reset.")

        time.sleep(60) # Check every minute

if __name__ == "__main__":
    print("Performing initial stock scrape before starting scheduler...")
    scrape_and_save_stocks() # Ensure JSON is populated
    print("Initial scrape complete.")
    run_scheduler()