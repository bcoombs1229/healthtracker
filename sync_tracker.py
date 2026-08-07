import os
import datetime
import json
import feedparser
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
import asyncio
# You will install this via: pip install renpho-api
from renpho_api import Renpho  

# --- 1. Renpho API Data ---
async def get_latest_renpho_weight(email, password):
    """Authenticates with Renpho and grabs the most recent weigh-in."""
    print("Connecting to Renpho...")
    try:
        renpho = Renpho(email, password)
        await renpho.authenticate()
        measurements = await renpho.get_measurements()
        
        if not measurements:
            return None, None
            
        latest = measurements[0]
        weight_lbs = round(latest.weight * 2.20462, 1)
        return weight_lbs, latest.bmi
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
    # Configure Gemini API
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
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
    
    try:
        response = model.generate_content(prompt)
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
    
    # Fetch Data
    weight, bmi = await get_latest_renpho_weight(renpho_email, renpho_password)
    title, exercises = get_and_parse_pushjerk(gemini_key)
    
    # Push to Sheets
    update_google_sheet(weight, bmi, title, exercises)
    print("Daily sync complete!")

if __name__ == "__main__":
    asyncio.run(main())
