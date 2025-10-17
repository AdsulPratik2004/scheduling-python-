from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import requests

load_dotenv()

app = FastAPI()

# ✅ Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/linkedin/token")
async def exchange_token(request: Request):
    body = await request.json()
    code = body.get("code")

    print("🔁 Received LinkedIn code:", code)

    params = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": os.getenv("REDIRECT_URI"),
        "client_id": os.getenv("LINKEDIN_CLIENT_ID"),
        "client_secret": os.getenv("LINKEDIN_CLIENT_SECRET"),
    }

    try:
        res = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data=params)
        print("🔗 Token exchange status:", res.status_code)
        print("🔗 Token exchange response:", res.text)
        res.raise_for_status()
        token_data = res.json()
        return token_data
    except requests.exceptions.RequestException as e:
        print("❌ Token exchange error:", str(e))
        return {"error": "Token exchange failed", "details": str(e)}

@app.post("/linkedin/post")
async def post_text(request: Request):
    body = await request.json()
    token = body.get("access_token")
    text = body.get("text")

    print("📝 Received post request")
    print("🔐 Token:", token)
    print("🗣️ Text:", text)

    if not token or not text:
        print("⚠️ Missing token or text")
        return {"error": "Missing access_token or text"}

    try:
        # ✅ CORRECTED: Use the userinfo endpoint for OpenID Connect
        profile_res = requests.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {token}"}
        )
        print("👤 Profile fetch status:", profile_res.status_code)
        print("👤 Profile fetch response:", profile_res.text)
        profile_res.raise_for_status()
        profile = profile_res.json()
        
        # ✅ CORRECTED: The user ID is in the 'sub' field for OpenID Connect
        author_urn = f"urn:li:person:{profile['sub']}"
        print("✅ Author URN:", author_urn)

        # ✅ Prepare post payload
        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }

        print("📦 Post payload:", payload)

        post_res = requests.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0"
            },
            json=payload
        )
        print("📤 Post response status:", post_res.status_code)
        print("📤 Post response body:", post_res.text)
        post_res.raise_for_status()
        return post_res.json()

    except requests.exceptions.RequestException as e:
        print("❌ LinkedIn post error:", str(e))
        return {"error": "LinkedIn post failed", "details": str(e)}