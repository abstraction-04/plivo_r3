# InspireWorks Plivo IVR Demo Application

This repository contains a Python (Flask)-based implementation of an interactive voice response (IVR) and OTP authentication system demonstrating the capabilities of the Plivo Voice API.

## Project Features
- **Outbound Calling Dashboard**: A responsive web interface styled with modern dark mode and glassmorphism.
- **Auto-Discovery Tunneling**: Automatically queries local `ngrok` metadata to determine and register the public callback URL.
- **OTP Authentication Layer**: Prompts and validates a hardcoded 4-digit security PIN (`1503`) using DTMF digits. If incorrect, it re-prompts the caller.
- **Multi-Level IVR Menu**:
  - **Level 1 (Language Selection)**: English (`1`) or Spanish (`2`).
  - **Level 2 (Actions)**: Play a hosted MP3 file (`1`) or connect to a live associate (`2`).
- **Real-Time Log Terminal**: Displays live call states and webhook events on the web page using Server-Sent Events (SSE).

---

## Setup & Running Instructions

### 1. Prerequisites
Ensure you have **Python 3.9+** installed.

### 2. Configuration
Create a `.env` file in the root directory with your Plivo details:

```env
PLIVO_AUTH_ID=<>
PLIVO_AUTH_TOKEN=<>
PLIVO_SOURCE_NUMBER=+918035454161
ASSOCIATE_NUMBER=02264236412
PORT=5000
```

### 3. Expose via Ngrok
In a separate terminal tab, run `ngrok` to expose your local port `5000` to the public internet:
```bash
ngrok http 5000
```
*Note: The application will automatically detect this tunnel URL via ngrok's local API. You do not need to manually configure it.*

### 4. Install & Start Server
Run the following commands in the project directory:
```bash
# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the Flask application
python main.py
```
Once the server starts, open [http://localhost:5005](http://localhost:5005) in your web browser.

---

## IVR Walkthrough Checklist

During the call, follow these steps to test the full flow:
1. **Answer** the call when it rings.
2. Enter an incorrect PIN (e.g. `1111`) first. Verify the bot prompts you again.
3. Enter the correct PIN **`1912`**. Verify it proceeds to language selection.
4. Press **`1`** for English, or **`2`** for Spanish.
5. In Level 2:
   - Press **`1`** to play the music audio file.
   - Press **`2`** to forward the call to the associate number (`02264236412`).
6. Observe real-time logs updating dynamically on your web dashboard terminal as you enter tones.
