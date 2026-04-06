from __future__ import annotations

import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def fetch_firebase_id_token(api_key: str, email: str, password: str) -> str:
    """
    Fetch Firebase ID token using email/password authentication.
    
    Args:
        api_key: Firebase Web API key
        email: User email
        password: User password
    
    Returns:
        Firebase ID token
    
    Raises:
        RuntimeError: If authentication fails
    """
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True,
    }

    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Firebase sign-in failed: {exc.code} {error_body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Firebase sign-in failed: {exc.reason}") from exc

    token = data.get("idToken")
    if not token:
        raise RuntimeError(f"Firebase sign-in response did not include idToken: {data}")
    return token
