DealHunt Streamlit Admin - Phase 1

Scope
- Admin login with Firebase bearer token
- Config via environment variables
- Backend connectivity checks for auth and admin routes

Files
- app.py: Streamlit entrypoint
- config.py: environment settings loader
- api_client.py: HTTP client with retries and timeout
- auth.py: login/session handling
- .env.example: required configuration template

Setup
1) Open terminal in backend/admin_streamlit
2) Create virtual env
   python -m venv venv
3) Activate env (PowerShell)
   .\venv\Scripts\Activate.ps1
4) Install dependencies
   pip install -r requirements.txt
5) Create .env
   copy .env.example .env
6) Set ADMIN_API_BASE_URL according to backend host

Run
streamlit run app.py

Login flow
1) Click Ping API to verify backend reachability
2) Paste Firebase ID token with admin claim enabled
3) Click Verify and Login
4) Check Admin Access should pass against /api/v1/admin/system/health

Notes
- Backend expects Authorization: Bearer <firebase_id_token>
- Admin rights are validated by Firebase custom claim admin=true and backend email whitelist
- Optional ADMIN_BEARER_TOKEN can be used for local development shortcut
