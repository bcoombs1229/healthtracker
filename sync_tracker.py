import os
import datetime
import feedparser
import gspread
from google.oauth2.service_account import Credentials
import asyncio
from renpho_api import Renpho  

async def get_latest_renpho_weight(email, password):
    """Authenticates with Renpho and grabs the most recent weigh-in."""
    print("Connecting to Renpho...")
    # Initialize Renpho client
    renpho = Renpho(email, password)
    await renpho.authenticate()
    
    # Get the latest measurements
    measurements = await renpho.get_measurements()
    if not measurements:
        return None, None
        
    latest = measurements[0]
    weight_kg = latest.weight
    # Convert kg to lbs (assuming you track in lbs)
    weight_lbs = round(weight_kg * 2.20462, 1)
    bmi = latest.bmi
    
    print(f"Latest weigh-in: {weight_lbs} lbs (BMI: {bmi})")
    return weight_lbs, bmi

def get_todays_pushjerk_workout():
    """Scrapes today's workout from Pushjerk's RSS feed."""
    print("Fetching today's Pushjerk WOD...")
    # Pushjerk is built on WordPress, which automatically generates an RSS feed
    feed_url = 'http://pushjerk.com/feed/'
    feed = feedparser.parse(feed_url)
    
    if not feed.entries:
        return "No workout posted yet."
        
    # The most recent post is the first entry
    latest_post = feed.entries[0]
    
    # Extract the title and link
    title = latest_post.title
    link = latest_post.link
    
    return f"{title}\n{link}"

def update_google_sheet(weight, bmi, pushjerk_wod):
    """Pushes the aggregated data into your Google Sheet."""
    print("Connecting to Google Sheets...")
    
    # Define the required scopes for Google Sheets
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # GitHub Actions will inject this JSON as an environment variable
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    
    if not creds_json:
        print("Skipping Sheets update: No Google credentials found.")
        return

    # Authenticate and connect
    creds = Credentials.from_service_account_info(eval(creds_json), scopes=scopes)
    client = gspread.authorize(creds)
    
    # Open the spreadsheet by its ID (found in your Google Sheet URL)
    SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
    sheet = client.open_by_key(SHEET_ID)
    
    # 1. Update the Daily Log with today's weight
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    daily_log = sheet.worksheet("Daily Log")
    
    # Append a new row: [Date, Weight, BMI, Workout Completed (False), Notes]
    daily_log.append_row([today_str, weight, bmi, "FALSE", ""])
    print("Updated Daily Log.")
    
    # 2. Update the Pushjerk Workouts tab
    pushjerk_tab = sheet.worksheet("Pushjerk Workouts")
    pushjerk_tab.append_row([today_str, pushjerk_wod])
    print("Updated Pushjerk WOD.")

async def main():
    # Grab Renpho credentials from secure environment variables
    renpho_email = os.environ.get("RENPHO_EMAIL")
    renpho_password = os.environ.get("RENPHO_PASSWORD")
    
    # Fetch Data
    weight, bmi = await get_latest_renpho_weight(renpho_email, renpho_password)
    pushjerk_wod = get_todays_pushjerk_workout()
    
    # Push to Sheets
    update_google_sheet(weight, bmi, pushjerk_wod)
    print("Daily sync complete!")

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
