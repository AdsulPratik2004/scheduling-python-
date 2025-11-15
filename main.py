import os
import json
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# --- Initialize Supabase ---
try:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY") # This MUST be your SERVICE_ROLE key
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase client initialized.")
except Exception as e:
    print(f"❌ FATAL: Supabase client failed to initialize: {e}")
    supabase = None

# --- CORS Configuration ---
origins = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:5173",
    "http://127.0.0.1:5173"
]
CORS(app, resources={r"/*": {"origins": origins}}, supports_credentials=True)

# -------------------- HELPER FOR ERROR CHECKING --------------------
def get_env_var(var_name):
    """Gets an env var or raises an error if missing."""
    value = os.getenv(var_name)
    if not value:
        print(f"❌ FATAL ERROR: Environment variable '{var_name}' is not set.")
        raise ValueError(f"Missing required config: {var_name}")
    return value

# -------------------- HELPER TO SAVE TOKEN (FINAL FIXED VERSION) --------------------
def save_token_to_supabase(user_id, platform, token_data):
    if not supabase:
        raise Exception("Supabase client is not initialized.")

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in") # Seconds as int

    expires_at = None
    if expires_in:
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()

    record_to_upsert = {
        "user_id": user_id,
        "platform": platform,
        "access_token": access_token,
        "refresh_token": refresh_token or None,
        "expires_at": expires_at
    }

    print(f"🔄 Upserting token for {platform} user {user_id}...")
    try:
        # This will raise an exception if it fails
        response = supabase.from_("social_connections") \
                             .upsert(record_to_upsert, on_conflict="user_id, platform") \
                             .execute()
        
        # If no exception was raised, it was successful.
        # The 'if response.error' check was the bug, so it is removed.
        
        print(f"✅ Token saved successfully. Response: {response.data}")
        return True # The function will now exit here successfully.

    except Exception as e:
        # This will now only catch REAL errors
        print(f"❌ Supabase save failed: {e}")
        raise e

# -------------------- FACEBOOK TOKEN EXCHANGE --------------------
@app.route("/facebook/token", methods=['POST'])
def exchange_facebook_token():
    try:
        data = request.get_json()
        code = data.get("code")
        user_id = data.get("userId")
        platform = data.get("platform")

        if not all([code, user_id, platform]):
            return jsonify({"error": "Missing 'code', 'userId', or 'platform'"}), 400

        print("🔁 Received Facebook code:", code)
        params = {
            "client_id": get_env_var("FACEBOOK_CLIENT_ID"),
            "client_secret": get_env_var("FACEBOOK_CLIENT_SECRET"),
            "redirect_uri": "http://localhost:8080/auth/callback", # <-- HARDCODED
            "code": code,
        }
        
        res = requests.get("https://graph.facebook.com/v24.0/oauth/access_token", params=params)
        res.raise_for_status()
        token_data = res.json()

        # Save to Supabase
        save_token_to_supabase(user_id, platform, token_data)
        
        return jsonify({"success": True})

    except requests.exceptions.RequestException as e:
        print(f"❌ Facebook token exchange error: {e.response.text if e.response else str(e)}")
        return jsonify({"error": "Facebook token exchange failed", "details": e.response.text if e.response else str(e)}), 500
    except Exception as e:
        print(f"❌ Server error: {str(e)}")
        return jsonify({"error": "An internal server error occurred", "details": str(e)}), 500

# -------------------- LINKEDIN TOKEN EXCHANGE --------------------
@app.route("/linkedin/token", methods=['POST'])
def exchange_linkedin_token():
    try:
        data = request.get_json()
        code = data.get("code")
        user_id = data.get("userId")
        platform = data.get("platform")

        if not all([code, user_id, platform]):
            return jsonify({"error": "Missing 'code', 'userId', or 'platform'"}), 400

        print("🔁 Received LinkedIn code:", code)
        params = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:8080/auth/callback", # <-- HARDCODED
            "client_id": get_env_var("LINKEDIN_CLIENT_ID"),
            "client_secret": get_env_var("LINKEDIN_CLIENT_SECRET"),
        }

        res = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data=params)
        res.raise_for_status()
        token_data = res.json()

        # Save to Supabase
        save_token_to_supabase(user_id, platform, token_data)

        return jsonify({"success": True})

    except requests.exceptions.RequestException as e:
        print(f"❌ LinkedIn token exchange error: {e.response.text if e.response else str(e)}")
        return jsonify({"error": "Token exchange failed", "details": e.response.text if e.response else str(e)}), 500
    except Exception as e:
        print(f"❌ Server error: {str(e)}")
        return jsonify({"error": "An internal server error occurred", "details": str(e)}), 500

# -------------------- YOUTUBE TOKEN EXCHANGE --------------------
@app.route("/youtube/token", methods=['POST'])
def exchange_youtube_token():
    try:
        data = request.get_json()
        code = data.get("code")
        user_id = data.get("userId")
        platform = data.get("platform")

        if not all([code, user_id, platform]):
            return jsonify({"error": "Missing 'code', 'userId', or 'platform'"}), 400

        print("🔁 Received YouTube code:", code)
        params = {
            "client_id": get_env_var("GOOGLE_CLIENT_ID"),
            "client_secret": get_env_var("GOOGLE_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": "http://localhost:8080/auth/callback", # <-- HARDCODED
        }
        
        res = requests.post("https://oauth2.googleapis.com/token", data=params)
        res.raise_for_status()
        token_data = res.json()

        # Save to Supabase
        save_token_to_supabase(user_id, platform, token_data)
        
        return jsonify({"success": True})

    except requests.exceptions.RequestException as e:
        print(f"❌ YouTube token exchange error: {e.response.text if e.response else str(e)}")
        return jsonify({"error": "Token exchange failed", "details": e.response.text if e.response else str(e)}), 500
    except Exception as e:
        print(f"❌ Server error: {str(e)}")
        return jsonify({"error": "An internal server error occurred", "details": str(e)}), 500

# --- Main entry point to run the app ---
if __name__ == "__main__":
    print("✅ Starting Flask backend server (Token Handler)...")
    app.run(port=8000, debug=True)