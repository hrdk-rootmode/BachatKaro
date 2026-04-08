from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import firebase_admin
from firebase_admin import auth, credentials


def initialize_firebase(service_account_path: Path) -> None:
    if firebase_admin._apps:
        return

    cred = credentials.Certificate(str(service_account_path))
    firebase_admin.initialize_app(cred)


def set_admin_claim(email: str) -> str:
    user = auth.get_user_by_email(email)
    auth.set_custom_user_claims(user.uid, {"admin": True})
    return user.uid


def fetch_firebase_id_token(api_key: str, email: str, password: str) -> str:
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Set Firebase admin claim and optionally print a fresh ID token for Streamlit login."
    )
    parser.add_argument("--email", required=True, help="Firebase user email to promote to admin")
    parser.add_argument(
        "--service-account",
        default="firebase-adminsdk.json",
        help="Path to Firebase service account JSON (default: firebase-adminsdk.json)",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Firebase Web API key for password sign-in (optional)",
    )
    parser.add_argument(
        "--password",
        default="",
        help="Firebase user password for fetching a fresh ID token (optional)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service_account_path = Path(args.service_account)

    if not service_account_path.exists():
        raise FileNotFoundError(f"Service account file not found: {service_account_path}")

    initialize_firebase(service_account_path)

    uid = set_admin_claim(args.email.lower())
    print(f"Admin claim set for {args.email} (uid: {uid})")

    if args.api_key and args.password:
        token = fetch_firebase_id_token(args.api_key, args.email, args.password)
        print()
        print("Fresh Firebase ID token:")
        print(token)
        print()
        print("Paste this token into the Streamlit admin login box.")
    else:
        print()
        print("Claim updated only.")
        print("If you need a fresh login token, run this script again with --api-key and --password.")


if __name__ == "__main__":
    main()