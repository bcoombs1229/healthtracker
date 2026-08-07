import os
import datetime
import json
import feedparser
import gspread
from google.oauth2.service_account import Credentials
from google import genai
import asyncio

# The updated library uses "from renpho import RenphoClient"
from renpho import RenphoClient  

# --- 1. Renpho API Data ---
def get_latest_renpho_weight(email, password):
    """Authenticates with Renpho and grabs the most recent weigh-in."""
    print("Connecting to Renpho...")
    try:
        # RenphoClient handles authentication synchronously now
        client = RenphoClient(email, password)
        client.login()
        
        # get_all_measurements() returns a list of dictionaries, newest first
        measurements = client.get_all_measurements()
        
        if not measurements:
            return None, None
            
        latest = measurements[0]
        # The new library might return weight directly in the app's unit. 
        # Assuming it returns Kg under the "weight" key based on the library docs.
        weight_kg = latest.get("weight")
        weight_lbs = round(weight_kg * 2.20462, 1) if weight_kg else None
        
        # BMI might not be directly available, fallback to None if missing
        bmi = latest.get("bmi", 0) 
        
        return weight_lbs, bmi
    except Exception as e:
        print(f"Renpho Error: {e}")
        return None, None

# --- 2. Pushjerk RSS Scraping & AI Parsing ---
def get_and_parse_pushjerk(gemini_api_key):
    """Scrapes today's workout and uses Gemini to format it into JSON."""
    print("Fetching today's Pushjerk WOD...")
    feed_url = 'http://pushjerk.com/feed/'
    feed = feedparser.parse(feed_url)
    
    if not feed.entries:
        return None, None
        
    latest_post = feed.entries[0]
    title = latest_post.title
    raw_text = latest_post.summary
    
    print("Parsing WOD with Gemini...")
    
    try:
        # Initialize the new google.genai client
        client = genai.Client(api_key=gemini_api_key)
        
        prompt = f"""
        You are a fitness data extraction bot. Read the following CrossFit workout description and extract the distinct exercises.
        Return ONLY a raw JSON array of objects. Do not include markdown formatting or backticks.
        Each object must have exactly these keys:
        "name": (String) The name of the exercise.
        "historyWeight": (String) Set to "Body" if it's a bodyweight movement, or "0" if it requires weight.
        "historyReps": (String) Set to "0".
        "trend": (String) Set to "same".
        
        Workout text to parse:
        {raw_text}
        """
        
        # Use the new generate_content syntax
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        
        # Clean up any potential markdown the AI accidentally includes
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        exercises = json.loads(clean_json)
        return title, exercises
    except Exception as e:
        print(f"Gemini Parsing Error: {e}")
        # Fallback if AI fails
        return title, [{"name": "Failed to parse. See Pushjerk.com", "historyWeight": "0", "historyReps": "0", "trend": "same"}]

# --- 3. Update Google Sheets ---
def update_google_sheet(weight, bmi, pushjerk_title, pushjerk_exercises):
    """Pushes the aggregated data into your Google Sheet Database."""
    print("Connecting to Google Sheets...")
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    
    if not creds_json:
        print("Skipping Sheets update: No Google credentials found.")
        return

    creds = Credentials.from_service_account_info(eval(creds_json), scopes=scopes)
    client = gspread.authorize(creds)
    SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
    sheet = client.open_by_key(SHEET_ID)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    # 1. Update WeightData Tab
    if weight and bmi:
        weight_sheet = sheet.worksheet("WeightData")
        weight_sheet.append_row([today_str, weight, bmi])
        print("Updated WeightData.")
    
    # 2. Update AvailableWorkouts Tab (Pushjerk)
    if pushjerk_title:
        workout_sheet = sheet.worksheet("AvailableWorkouts")
        # Format: Date, Program, Title, JSON_Exercises
        workout_sheet.append_row([today_str, "Pushjerk", pushjerk_title, json.dumps(pushjerk_exercises)])
        print("Updated AvailableWorkouts (Pushjerk).")

async def main():
    # Grab Secrets from environment
    renpho_email = os.environ.get("RENPHO_EMAIL")
    renpho_password = os.environ.get("RENPHO_PASSWORD")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    # Fetch Data (renpho is no longer async in the updated package)
    weight, bmi = get_latest_renpho_weight(renpho_email, renpho_password)
    title, exercises = get_and_parse_pushjerk(gemini_key)
    
    # Push to Sheets
    update_google_sheet(weight, bmi, title, exercises)
    print("Daily sync complete!")

if __name__ == "__main__":
    # We no longer strictly need asyncio if the packages dropped async support, 
    # but we can leave the runner here to execute main()
    asyncio.run(main())
