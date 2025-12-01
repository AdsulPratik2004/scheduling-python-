import os
import json
import requests
from urllib.parse import urlencode
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

# -------------------- HELPER TO SAVE TOKEN --------------------
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
        response = supabase.from_("social_connections") \
                             .upsert(record_to_upsert, on_conflict="user_id, platform") \
                             .execute()
        
        print(f"✅ Token saved successfully.")
        return True 

    except Exception as e:
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
        redirect_uri = data.get("redirect_uri")

        if not all([code, user_id, platform]):
            return jsonify({"error": "Missing 'code', 'userId', or 'platform'"}), 400
        
        # Default fallback if frontend doesn't send it, but frontend SHOULD send it
        if not redirect_uri:
            print("⚠️ WARNING: No redirect_uri received from frontend. Defaulting to localhost:8080.")
            redirect_uri = "http://localhost:8080/auth/callback"

        print("🔁 Received Facebook code:", code)
        print(f"   Using redirect_uri: {redirect_uri}")

        params = {
            "client_id": get_env_var("FACEBOOK_CLIENT_ID"),
            "client_secret": get_env_var("FACEBOOK_CLIENT_SECRET"),
            "redirect_uri": redirect_uri, 
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
        
        # 1. Validation
        if not data:
            return jsonify({"error": "No JSON data received"}), 400
            
        code = data.get("code")
        user_id = data.get("userId")
        platform = data.get("platform")
        redirect_uri_param = data.get("redirect_uri") # Crucial
        code_verifier = data.get("code_verifier") 

        if not all([code, user_id, platform]):
            return jsonify({"error": "Missing required fields (code, userId, platform)"}), 400

        # 2. Determine Redirect URI
        # The logs showed a mismatch. We prioritize the URI sent from the frontend.
        redirect_uri = None
        if redirect_uri_param:
            redirect_uri = redirect_uri_param.strip()
            print(f"✅ Using redirect_uri from request: {redirect_uri}")
        else:
            # Fallback (This usually causes the 400 error if it doesn't match frontend)
            redirect_uri = os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:8080/auth/callback")
            print(f"⚠️  WARNING: Using fallback redirect_uri: {redirect_uri}. Ensure this matches your frontend!")

        # 3. Prepare Payload
        client_id = get_env_var("LINKEDIN_CLIENT_ID")
        client_secret = get_env_var("LINKEDIN_CLIENT_SECRET")
        
        token_url = "https://www.linkedin.com/oauth/v2/accessToken"
        
        payload = {
            "grant_type": "authorization_code",
            "code": code.strip(),
            "redirect_uri": redirect_uri, 
            "client_id": client_id,
            "client_secret": client_secret,
        }
        
        if code_verifier:
            payload["code_verifier"] = code_verifier.strip()
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        
        print(f"🔄 Exchanging LinkedIn token...")
        
        # 4. Execute Request
        res = requests.post(token_url, data=payload, headers=headers, timeout=30)
        
        # 5. Handle Errors
        if res.status_code != 200:
            print(f"❌ LinkedIn Error {res.status_code}: {res.text}")
            return jsonify({
                "error": "LinkedIn token exchange failed", 
                "details": res.text,
                "hint": f"Ensure '{redirect_uri}' matches EXACTLY the URI used in your frontend logic."
            }), res.status_code

        token_data = res.json()
        
        # 6. Save to DB
        save_token_to_supabase(user_id, platform, token_data)

        print(f"✅ LinkedIn token exchange successful for user {user_id}")
        return jsonify({"success": True, "message": "Token saved successfully"})

    except Exception as e:
        print(f"❌ Server error: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

# -------------------- YOUTUBE TOKEN EXCHANGE --------------------
@app.route("/youtube/token", methods=['POST'])
def exchange_youtube_token():
    try:
        data = request.get_json()
        code = data.get("code")
        user_id = data.get("userId")
        platform = data.get("platform")
        redirect_uri = data.get("redirect_uri")

        if not all([code, user_id, platform]):
            return jsonify({"error": "Missing 'code', 'userId', or 'platform'"}), 400

        # Default fallback
        if not redirect_uri:
            print("⚠️ WARNING: No redirect_uri received from frontend. Defaulting to localhost:8080.")
            redirect_uri = "http://localhost:8080/auth/callback"

        print("🔁 Received YouTube code:", code)
        print(f"   Using redirect_uri: {redirect_uri}")

        params = {
            "client_id": get_env_var("GOOGLE_CLIENT_ID"),
            "client_secret": get_env_var("GOOGLE_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri, 
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

if __name__ == "__main__":
    print("✅ Starting Flask backend server (Token Handler)...")
    app.run(port=8000, debug=True)
