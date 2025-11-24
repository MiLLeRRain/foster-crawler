# SPCA Foster Monitor 🐾

A robust, automated monitoring system running on GitHub Actions to detect "Foster" opportunities on the Wellington SPCA website. It uses **Playwright** for visual rendering and **Google Gemini 3 Pro (Vision)** to analyze webpage screenshots, ensuring high stability against DOM changes.

## Features

- 🕒 **Smart Scheduling**: Runs every 30 minutes within specified operating hours (default 08:00 - 20:00 NZT).
- 👁️ **AI Vision Analysis**: Uses Gemini 3 Pro to "see" the page, identifying animals and their status ("Pending" vs "Ask to foster").
- 🛡️ **Deduplication**: Maintains a `history.txt` to prevent repeated alerts for the same animal.
- 🔔 **Push Notifications**: Sends real-time alerts via PushPlus to WeChat.
- ⚙️ **Configurable**: Fully configurable via GitHub Repository Variables without changing code.

## Setup Guide

### 1. Fork or Clone
Fork this repository to your own GitHub account.

### 2. Get API Keys
- **Gemini API Key**: Get one from [Google AI Studio](https://aistudio.google.com/).
- **PushPlus Token**: Get one from [PushPlus](http://www.pushplus.plus/).

### 3. Configure GitHub Secrets
Go to your repository **Settings** -> **Secrets and variables** -> **Actions** -> **Repository secrets**.
Add the following secrets:

| Secret Name | Value | Description |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | `AIzaSy...` | Your Google Gemini API Key. |
| `PUSHPLUS_TOKEN` | `abc123...` | Your PushPlus User Token. |
| `TARGET_URLS` | `["https://..."]` | JSON list of URLs to monitor. **(Moved to Secrets for privacy)** |

### 4. Configure GitHub Variables (Optional)
Go to **Settings** -> **Secrets and variables** -> **Actions** -> **Repository variables**.
You can customize the behavior by adding these variables. If not set, defaults will be used.

| Variable Name | Default Value | Description |
| :--- | :--- | :--- |
| `START_HOUR` | `8` | Start hour of the day (0-23) in NZT. |
| `END_HOUR` | `20` | End hour of the day (0-23) in NZT. |
| `OPERATING_DAYS`| `0,1,2,3,4,5,6` | Days of the week to run (0=Monday, 6=Sunday). Example: `0,1,2,3,4` for weekdays only. |
| `DETECTION_RULES` | *(Default Rule)* | Natural language rules for LLM filtering. Example: `Include ONLY items where the button text contains 'Ask' or 'Available'.` |
| `DEBUG_LLM` | `false` | Set to `true` to print the full LLM prompt and response to the logs for debugging. |
| `GEMINI_MODEL` | `gemini-3-pro-preview` | The primary Gemini model to use. Falls back to `gemini-1.5-pro` if it fails. |

## Manual Testing

You can manually trigger the workflow from the **Actions** tab in GitHub.

1. Go to **Actions** -> **Monitor Foster Opportunities**.
2. Click **Run workflow**.
3. You have two options:
    - **Force run (ignore time)**: Check this to run the crawler immediately, ignoring the time window.
    - **Test PushPlus notification**: Check this to send a test alert to verify your PushPlus token.

## Local Development

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Set Environment Variables**:
   ```powershell
   $env:GEMINI_API_KEY="your_key"
   $env:PUSHPLUS_TOKEN="your_token"
   ```

3. **Run Script**:
   ```bash
   # Normal run
   python main.py

   # Force run (ignore time)
   python main.py --force

   # Test notification
   python main.py --test-push
   ```
