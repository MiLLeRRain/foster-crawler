import os
import sys
import json
import re
import time
import base64
import argparse
from datetime import datetime
import pytz
import requests
from playwright.sync_api import sync_playwright
from google import genai
from google.genai import types

# Configuration
# Load config from environment variables. Fail if missing.
try:
    TARGET_URLS = json.loads(os.environ["TARGET_URLS"])
except KeyError:
    print("Error: TARGET_URLS environment variable is missing.")
    sys.exit(1)
except json.JSONDecodeError:
    # Fallback to comma-separated if JSON fails
    TARGET_URLS = [u.strip() for u in os.environ.get("TARGET_URLS", "").split(",") if u.strip()]
    if not TARGET_URLS:
        print("Error: TARGET_URLS is invalid or empty.")
        sys.exit(1)

HISTORY_FILE = "history.txt"
TIMEZONE = "Pacific/Auckland"

# Operating Window Config
try:
    START_HOUR = int(os.environ["START_HOUR"])
    END_HOUR = int(os.environ["END_HOUR"])
    # Days: 0=Monday, 6=Sunday.
    OPERATING_DAYS = [int(d) for d in os.environ["OPERATING_DAYS"].split(",") if d.strip().isdigit()]
except KeyError as e:
    print(f"Error: Missing required environment variable: {e}")
    sys.exit(1)
except ValueError:
    print("Error: Invalid format for time/day config.")
    sys.exit(1)

# Detection Config
# Natural language rules for detection.
# e.g. "Include ONLY items where the button text contains 'Ask to foster' or 'Available'."
DETECTION_RULES = os.environ.get("DETECTION_RULES", "Include ONLY items where the button text contains 'Ask' (case-insensitive).")

# Debug Config
DEBUG_LLM = os.environ.get("DEBUG_LLM", "false").lower() == "true"

# Model Config
PRIMARY_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-pro-preview")
FALLBACK_MODEL = "gemini-2.5-pro"

def check_operating_hours():
    """Exit if outside operating window (Time or Day)."""
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    
    # Check Day of Week
    if now.weekday() not in OPERATING_DAYS:
        print(f"Today is {now.strftime('%A')} (Day {now.weekday()}), which is not in operating days {OPERATING_DAYS}. Exiting.")
        sys.exit(0)

    # Check Time
    if not (START_HOUR <= now.hour < END_HOUR):
        print(f"Current time {now.strftime('%H:%M')} is outside operating hours ({START_HOUR}-{END_HOUR}). Exiting.")
        sys.exit(0)
    print(f"Operating within window: {now.strftime('%H:%M')} on {now.strftime('%A')}")

def load_history():
    """Load history from file."""
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_history(new_key):
    """Append new key to history file."""
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{new_key}\n")

def normalize_key(id_text):
    """
    Generate a stable unique key.
    1. If digits > 3 chars exist (e.g. '649991'), use them.
    2. Else, normalize string (lowercase, alphanumeric only).
    """
    # Look for sequence of 4 or more digits
    digit_match = re.search(r'\d{4,}', id_text)
    if digit_match:
        return digit_match.group(0)
    
    # Fallback: normalize string
    return re.sub(r'[^a-z0-9]', '', id_text.lower())

def send_notification(title, content):
    """Send notification via PushPlus."""
    token = os.environ.get("PUSHPLUS_TOKEN")
    if not token:
        print("Warning: PUSHPLUS_TOKEN not set. Skipping notification.")
        return

    url = "http://www.pushplus.plus/send"
    payload = {
        "token": token,
        "title": title,
        "content": content
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        print(f"Notification sent: {title}")
    except Exception as e:
        print(f"Failed to send notification: {e}")

def analyze_screenshot(client, image_bytes):
    """Send screenshot to Gemini for analysis."""
    prompt = (
        f"Identify animal listing blocks in the image.\n"
        f"CRITICAL FILTERING RULES:\n"
        f"{DETECTION_RULES}\n\n"
        "For each matching block, extract:\n"
        "1. The primary identifier text below the image (e.g., 'AID 649991 - Hinau' or '3x Puppies').\n"
        "2. The exact button text at the bottom.\n"
        "Return strictly a JSON list: [{'id': '...', 'status': '...'}]"
    )

    if DEBUG_LLM:
        print(f"\n[DEBUG] LLM Prompt:\n{prompt}\n")

    try:
        # Create the image part using types.Part with inline_data
        # This matches the latest v1alpha SDK usage for high resolution
        image_part = types.Part(
            inline_data=types.Blob(
                mime_type="image/png",
                data=image_bytes
            ),
            media_resolution={"level": "media_resolution_high"}
        )
        
        def call_model(model_name):
            return client.models.generate_content(
                model=model_name,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=prompt),
                            image_part
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

        try:
            response = call_model(PRIMARY_MODEL)
        except Exception as e:
            print(f"Primary model '{PRIMARY_MODEL}' failed: {e}")
            print(f"Falling back to '{FALLBACK_MODEL}'...")
            response = call_model(FALLBACK_MODEL)
        
        if DEBUG_LLM:
            print(f"\n[DEBUG] LLM Response:\n{response.text}\n")

        return json.loads(response.text)
    except Exception as e:
        print(f"Gemini analysis failed: {e}")
        return []

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Ignore time window restrictions")
    parser.add_argument("--test-push", action="store_true", help="Send a test notification and exit")
    args = parser.parse_args()

    if args.test_push:
        print("Sending test notification...")
        send_notification("Test Notification", "This is a test message from the Foster Crawler to verify PushPlus integration.")
        return

    if not args.force:
        check_operating_hours()
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set.")
        sys.exit(1)

    # Initialize Gemini Client (v1alpha)
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(api_version='v1alpha')
    )

    history = load_history()
    new_findings = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        
        for i, url in enumerate(TARGET_URLS):
            # Mask URL in logs if it's a secret (GitHub Actions masks secrets automatically, 
            # but we also use a generic label here for cleaner logs)
            log_label = f"Target [{i+1}]"
            print(f"Checking {log_label}...")
            page = context.new_page()
            try:
                page.goto(url)
                # Critical wait for images to load
                page.wait_for_timeout(8000)
                
                screenshot = page.screenshot(full_page=True)
                print("Screenshot taken. Analyzing with Gemini...")
                
                items = analyze_screenshot(client, screenshot)
                print(f"Found {len(items)} items.")
                
                for item in items:
                    raw_id = item.get('id', '').strip()
                    status = item.get('status', '').strip()
                    
                    # Filter logic is now handled by LLM prompt
                        
                    unique_key = normalize_key(raw_id)
                    
                    if unique_key and unique_key not in history:
                        print(f"New Opportunity: {raw_id} (Key: {unique_key})")
                        new_findings.append(f"{raw_id} [{status}]")
                        save_history(unique_key)
                        history.add(unique_key)
                        
                        # Send individual notification or batch later? 
                        # Requirement says "If new: Send Notification -> Save unique_key".
                        # We'll send immediately to be safe.
                        send_notification(
                            title="New Foster Opportunity!",
                            content=f"Found: {raw_id}<br>Status: {status}<br>Link: {url}"
                        )
                    else:
                        print(f"Skipping (Known or Invalid): {raw_id}")
                        
            except Exception as e:
                print(f"Error processing {log_label}: {e}")
            finally:
                page.close()
        
        browser.close()

if __name__ == "__main__":
    main()
