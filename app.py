import os
import json
from flask import Flask, request
from dotenv import load_dotenv
import africastalking
from db import init_db, add_subscriber, remove_subscriber, get_subscriber, \
                    update_subscribed_stocks, update_notification_preference, get_all_subscribers
# Keeping scrape_and_save_stocks import for potential future on-demand use,
# but it's not used directly for initial data loading in this file.

load_dotenv() # Load environment variables from .env file

# --- AfricasTalking API Configuration ---
# Ensure these match your .env keys (e.g., AT_USERNAME, AT_API_KEY, AT_SENDER_ID)
AT_USERNAME = os.getenv("username")
AT_API_KEY = os.getenv("api_key")
AT_SENDER_ID = os.getenv("AT_SENDER_ID")

# Initialize AfricasTalking SDK
try:
    if not AT_USERNAME or not AT_API_KEY:
        raise ValueError("AT_USERNAME or AT_API_KEY environment variables not set.")
    africastalking.initialize(AT_USERNAME, AT_API_KEY)
    sms = africastalking.SMS
    print("AfricasTalking SDK initialized successfully in app.py")
except Exception as e:
    print(f"Error initializing AfricasTalking SDK in app.py: {e}")
    print("Ensure AT_USERNAME and AT_API_KEY are correctly set in your .env file.")
    # In a production app, you might want to log this and keep running
    # but for a critical dependency, exiting might be appropriate.
    exit(1)

app = Flask(__name__)

# Global variable to hold loaded stock data
CURRENT_STOCKS_DATA = []
STOCKS_JSON_FILE = "cleaned_stock_prices.json"

def load_stocks_data():
    """
    Loads cleaned stock data from a JSON file.
    Expects the JSON file to contain a dictionary with a 'stocks' key
    holding a list of stock dictionaries, or directly a list of stock dictionaries.
    """
    global CURRENT_STOCKS_DATA
    if os.path.exists(STOCKS_JSON_FILE):
        try:
            with open(STOCKS_JSON_FILE, 'r') as f:
                file_content = f.read()
                if file_content: # Check if file is not empty
                    data = json.loads(file_content)
                    
                    # Check if data is a dictionary and contains the 'stocks' key
                    if isinstance(data, dict) and "stocks" in data:
                        CURRENT_STOCKS_DATA = data["stocks"]
                    elif isinstance(data, list): # Fallback if JSON is just a list
                        CURRENT_STOCKS_DATA = data
                    else:
                        print(f"Warning: Unexpected JSON structure in {STOCKS_JSON_FILE}. Expected a list or a dict with 'stocks' key.")
                        CURRENT_STOCKS_DATA = [] # Reset to empty list if structure is unexpected

                    print(f"Loaded {len(CURRENT_STOCKS_DATA)} stocks from {STOCKS_JSON_FILE}")
                else:
                    print(f"Warning: {STOCKS_JSON_FILE} is empty.")
                    CURRENT_STOCKS_DATA = []
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from {STOCKS_JSON_FILE}: {e}")
            CURRENT_STOCKS_DATA = []
    else:
        print(f"Warning: {STOCKS_JSON_FILE} not found. Scrape to generate it. USSD might not show current prices.")
        CURRENT_STOCKS_DATA = [] # Ensure it's an empty list if file is missing

# --- Helper Functions for USSD Responses ---

def main_menu_response():
    """Returns the main USSD menu."""
    response = "CON Welcome to Share Price Tracker!\n"
    response += "1. Subscribe\n"
    response += "2. View Stocks\n"
    response += "3. My Subscriptions\n"
    response += "4. Unsubscribe"
    return response

def display_stocks_menu(phone_number, current_text_path=''):
    """
    Helper to display stocks for subscription or viewing.
    current_text_path is used to maintain the correct USSD navigation path.
    """
    global CURRENT_STOCKS_DATA
    if not CURRENT_STOCKS_DATA:
        load_stocks_data() # Try to load if not already loaded

    if not CURRENT_STOCKS_DATA:
        return "No stock data available at the moment. Please try again later."
    
    menu = "Available Stocks:\n"
    # Limit to 10 for USSD readability (adjust as needed)
    for i, stock in enumerate(CURRENT_STOCKS_DATA[:10]):
        menu += f"{i+1}. {stock['name']}\n"
    
    menu += "Enter stock number to select.\n"
    # Append the back option based on the current text path
    menu += f"0. Back to Main Menu" # More general for now, specific back paths can be added if needed
    return menu

def handle_stock_selection(phone_number, text):
    """
    Handles stock selection for new subscriptions (path '1*X').
    Also used for adding stocks in 'My Subscriptions' ('3*1*add*X').
    """
    parts = text.split('*')
    # The last part is the user's input, the second to last determines context
    selected_option = parts[-1]
    
    # Determine the base path for returning to the stock list if input is invalid
    # This is a bit of a hack for generic back path, consider refining based on actual USSD flow
    if len(parts) >= 2:
        # Reconstruct base path, e.g., '1' for subscribe, '3*1*add' for managing
        base_path_for_retry = "*".join(parts[:-1])
    else:
        base_path_for_retry = "1" # Default for initial subscription

    if selected_option == '0':
        return main_menu_response()

    try:
        index = int(selected_option) - 1
        if 0 <= index < len(CURRENT_STOCKS_DATA):
            selected_stock_name = CURRENT_STOCKS_DATA[index]['name']
            
            subscriber = get_subscriber(phone_number)
            if not subscriber:
                return "END Error: Subscriber not found. Please re-subscribe."

            subscribed_stocks = json.loads(subscriber[1])
            if selected_stock_name not in subscribed_stocks:
                subscribed_stocks.append(selected_stock_name)
                update_subscribed_stocks(phone_number, json.dumps(subscribed_stocks))
                response = f"CON Successfully subscribed to {selected_stock_name}.\n"
            else:
                response = f"CON You are already subscribed to {selected_stock_name}.\n"
            
            # Offer to subscribe to another or go back
            response += "1. Subscribe to another stock\n"
            response += "0. Back to Main Menu" # This might need to be dynamic to return to prev menu
            return response
        else:
            return f"CON Invalid stock number. Please try again.\n" + display_stocks_menu(phone_number, current_text_path=base_path_for_retry)
    except ValueError:
        return f"CON Invalid input. Please enter a number.\n" + display_stocks_menu(phone_number, current_text_path=base_path_for_retry)

def handle_view_stock_details(phone_number, text):
    """Handles viewing individual stock details (path '2*X')."""
    parts = text.split('*')
    selected_option = parts[-1]

    if selected_option == '0':
        return main_menu_response()
    
    try:
        index = int(selected_option) - 1
        if 0 <= index < len(CURRENT_STOCKS_DATA):
            stock = CURRENT_STOCKS_DATA[index]
            # Use END to terminate session after showing details
            response = f"END {stock['name']}: Ksh {stock['price']:.2f}\n"
            response += "Data in real-time."
            return response
        else:
            return "CON Invalid stock number. Please try again.\n" + display_stocks_menu(phone_number, current_text_path='2')
    except ValueError:
        return "CON Invalid input. Please enter a number.\n" + display_stocks_menu(phone_number, current_text_path='2')

def handle_manage_subscribed_stocks(phone_number, text):
    """Handles adding or removing stocks from a subscriber's list (path '3*1*X' or '3*1*add*X')."""
    parts = text.split('*')
    action = parts[-1] # This will be the stock number to remove or 'add' or the selected stock number after 'add'

    subscriber = get_subscriber(phone_number)
    if not subscriber:
        return "END Error: Subscriber not found. Please re-subscribe."

    subscribed_stocks = json.loads(subscriber[1])

    if action == '0': # Back to Main Menu
        return main_menu_response()
    elif action.lower() == 'add':
        response = "CON Select stocks to add:\n"
        # The path for adding is '3*1*add' so it knows where to go back
        response += display_stocks_menu(phone_number, current_text_path='3*1*add')
        return response
    elif len(parts) >= 3 and parts[2].lower() == 'add' and action.isdigit(): # User selected a stock to add after '3*1*add*'
        return handle_stock_selection(phone_number, f"1*{action}") # Reuse existing logic for adding a stock
    else: # Attempt to remove a stock by number
        try:
            remove_index = int(action) - 1
            if 0 <= remove_index < len(subscribed_stocks):
                removed_stock = subscribed_stocks.pop(remove_index)
                update_subscribed_stocks(phone_number, json.dumps(subscribed_stocks))
                response = f"CON Removed {removed_stock} from your subscriptions.\n"
                response += "1. Manage Subscribed Stocks\n"
                response += "2. Set Notification Preferences\n"
                response += "0. Back to Main Menu" # Back to My Subscriptions sub-menu
                return response
            else:
                # Re-display current subscriptions with an error message
                current_subs_display = "\n".join([f"{i+1}. {s}" for i, s in enumerate(subscribed_stocks)])
                return f"CON Invalid stock number to remove. Please try again.\nYour current subscriptions:\n{current_subs_display}\nEnter stock number to remove, or 'add' to add new stocks.\n0. Back to Main Menu"
        except ValueError:
            # Re-display current subscriptions with an error message
            current_subs_display = "\n".join([f"{i+1}. {s}" for i, s in enumerate(subscribed_stocks)])
            return f"CON Invalid input. Please enter a number or 'add'.\nYour current subscriptions:\n{current_subs_display}\nEnter stock number to remove, or 'add' to add new stocks.\n0. Back to Main Menu"

def handle_notification_preference(phone_number, text):
    """Handles toggling market open/close notification preferences (path '3*2*X')."""
    parts = text.split('*')
    option = parts[-1]

    subscriber = get_subscriber(phone_number)
    if not subscriber:
        return "END Error: Subscriber not found. Please re-subscribe."
    
    # Subscriber tuple structure: (phone_number, subscribed_stocks_json, market_open_notify, market_close_notify)
    current_market_open = subscriber[2]
    current_market_close = subscriber[3]

    response = "CON Set Notification Preferences:\n"

    if option == '1': # Toggle Market Open
        new_value = 1 if current_market_open == 0 else 0
        update_notification_preference(phone_number, 'market_open_notify', new_value)
        response += f"1. Market Open: {'ON' if new_value else 'OFF'}\n"
        response += f"2. Market Close: {'ON' if current_market_close else 'OFF'}\n"
        response += "Select an option to toggle.\n"
        response += "0. Back to Main Menu"
    elif option == '2': # Toggle Market Close
        new_value = 1 if current_market_close == 0 else 0
        update_notification_preference(phone_number, 'market_close_notify', new_value)
        response += f"1. Market Open: {'ON' if current_market_open else 'OFF'}\n"
        response += f"2. Market Close: {'ON' if new_value else 'OFF'}\n"
        response += "Select an option to toggle.\n"
        response += "0. Back to Main Menu"
    elif option == '0':
        return main_menu_response()
    else:
        response = "CON Invalid option. Please select 1 or 2.\n"
        response += f"1. Market Open: {'ON' if current_market_open else 'OFF'}\n"
        response += f"2. Market Close: {'ON' if current_market_close else 'OFF'}\n"
        response += "Select an option to toggle.\n"
        response += "0. Back to Main Menu"
    return response

# Helper function to send SMS
def send_sms(to_number, message):
    """Sends an SMS message using AfricasTalking SDK."""
    global sms # Declare sms as global to access the initialized SDK object
    try:
        recipients = [to_number]
        
        if AT_SENDER_ID: # Use the configured SENDER_ID if available
            response = sms.send(message, recipients, senderId=AT_SENDER_ID)
        else:
            response = sms.send(message, recipients)
        print(f"SMS sent to {to_number}: {response}")
        return True
    except Exception as e:
        print(f"Error sending SMS to {to_number}: {e}")
        return False

# --- Main USSD Callback Route ---
@app.route('/ussd', methods=['GET','POST'])
def ussd_callback():
    """Handles USSD requests from AfricasTalking."""
    session_id = request.values.get("sessionId")
    service_code = request.values.get("serviceCode")
    phone_number = request.values.get("phoneNumber")
    text = request.values.get("text", "") # Default to empty string for initial request

    response = ""

    if text == '': # Initial request
        response = main_menu_response()
    elif text == '1': # Subscribe
        subscriber = get_subscriber(phone_number)
        if subscriber:
            response = "END You are already subscribed! Choose '3' to manage your subscriptions."
        else:
            add_subscriber(phone_number)
            response = "CON You have successfully subscribed!\n"
            response += "Now, let's select stocks to track.\n"
            response += display_stocks_menu(phone_number, current_text_path='1')
    elif text.startswith('1*'): # After initial subscription, selecting stocks or adding more
        response = handle_stock_selection(phone_number, text)
    elif text == '2': # View Stocks (for non-subscribers or general Browse)
        response = "CON " + display_stocks_menu(phone_number, current_text_path='2')
    elif text.startswith('2*'): # Selecting stocks to view (temporary, not for subscription)
        response = handle_view_stock_details(phone_number, text)
    elif text == '3': # My Subscriptions
        subscriber = get_subscriber(phone_number)
        if not subscriber:
            response = "END You are not subscribed. Dial again and select '1' to subscribe."
        else:
            response = "CON My Subscriptions:\n"
            response += "1. Manage Subscribed Stocks\n"
            response += "2. Set Notification Preferences\n"
            response += "0. Back to Main Menu"
    elif text == '3*1': # Manage Subscribed Stocks
        subscriber = get_subscriber(phone_number)
        if subscriber:
            subscribed_stocks = json.loads(subscriber[1])
            if not subscribed_stocks:
                response = "CON You have no stocks subscribed yet.\n"
                response += display_stocks_menu(phone_number, current_text_path='3*1') # Offer to subscribe
            else:
                response = "CON Your current subscriptions:\n"
                for i, stock_name in enumerate(subscribed_stocks):
                    response += f"{i+1}. {stock_name}\n"
                response += "--- Add/Remove ---\n"
                response += "Enter stock number to remove, or 'add' to add new stocks.\n"
                response += "0. Back to Main Menu"
        else:
            response = "END Error: Subscriber not found." # Should not happen if '3' is checked
    elif text.startswith('3*1*'): # Add/Remove subscribed stocks
        response = handle_manage_subscribed_stocks(phone_number, text)
    elif text == '3*2': # Set Notification Preferences
        subscriber = get_subscriber(phone_number)
        if subscriber:
            market_open_notify = subscriber[2]
            market_close_notify = subscriber[3]
            response = "CON Set Notification Preferences:\n"
            response += f"1. Market Open: {'ON' if market_open_notify else 'OFF'}\n"
            response += f"2. Market Close: {'ON' if market_close_notify else 'OFF'}\n"
            response += "Select an option to toggle.\n"
            response += "0. Back to Main Menu"
        else:
            response = "END Error: Subscriber not found."
    elif text.startswith('3*2*'): # Toggle notification preferences
        response = handle_notification_preference(phone_number, text)
    elif text == '4': # Unsubscribe
        remove_subscriber(phone_number)
        response = "END You have successfully unsubscribed from Stock Price Tracker. Goodbye!"
    else:
        response = "END Invalid input. Please try again."

    return response

# --- Application Initialization ---
if __name__ == '__main__':
    # Initialize the database and load stocks on startup
    init_db()
    load_stocks_data() # This will load data for the USSD menu from the JSON file

    print("Starting Flask USSD Application...")
    # Using debug=True for development. Disable in production.
    app.run(host='0.0.0.0', port=8080, debug=True)
    # IMPORTANT: Do not run the scheduler here. It should be a separate process.