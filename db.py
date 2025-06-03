import sqlite3

DATABASE_NAME = 'stock_subscribers.db'

def init_db():
    """Initializes the SQLite database and creates the subscribers table."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            phone_number TEXT PRIMARY KEY,
            subscribed_stocks TEXT, -- Stores JSON string of stock symbols
            market_open_notify INTEGER DEFAULT 0, -- 1 for true, 0 for false
            market_close_notify INTEGER DEFAULT 0 -- 1 for true, 0 for false
        )
    ''')
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

def add_subscriber(phone_number):
    """Adds a new subscriber to the database."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO subscribers (phone_number, subscribed_stocks) VALUES (?, ?)",
                       (phone_number, "[]")) # Initialize with empty list of subscribed stocks
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        print(f"Subscriber {phone_number} already exists.")
        return False
    finally:
        conn.close()

def remove_subscriber(phone_number):
    """Removes a subscriber from the database."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM subscribers WHERE phone_number = ?", (phone_number,))
    conn.commit()
    conn.close()
    print(f"Subscriber {phone_number} removed.")

def get_subscriber(phone_number):
    """Retrieves a subscriber's details."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subscribers WHERE phone_number = ?", (phone_number,))
    subscriber = cursor.fetchone()
    conn.close()
    return subscriber

def update_subscribed_stocks(phone_number, stocks_json):
    """Updates the list of subscribed stocks for a subscriber."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE subscribers SET subscribed_stocks = ? WHERE phone_number = ?",
                   (stocks_json, phone_number))
    conn.commit()
    conn.close()

def update_notification_preference(phone_number, preference_type, value):
    """Updates market open/close notification preferences."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    query = f"UPDATE subscribers SET {preference_type} = ? WHERE phone_number = ?"
    cursor.execute(query, (value, phone_number))
    conn.commit()
    conn.close()

def get_all_subscribers():
    """Retrieves all subscribers."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT phone_number, subscribed_stocks, market_open_notify, market_close_notify FROM subscribers")
    subscribers = cursor.fetchall()
    conn.close()
    return subscribers

if __name__ == '__main__':
    init_db()