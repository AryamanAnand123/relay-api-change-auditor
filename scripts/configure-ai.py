"""Enter a Groq key in a local terminal; never put the key in command arguments."""

import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from auditor.config import Settings


def main():
    if not sys.stdin.isatty():
        raise SystemExit("Run this script in an interactive local terminal so the key can be entered without echo.")
    settings = Settings()
    directory = settings.runtime_root
    if not (directory / ".api-auditor-runtime").is_file():
        raise SystemExit("Run scripts/setup-history.py first to prepare the private runtime folder.")
    print("Create a key at https://console.groq.com/keys using a Free-plan account.")
    print("Do not upgrade or add billing for this project. The app cannot inspect your account's billing plan.")
    print("On your explicit request, selected finding evidence will be sent to Groq for an AI explanation.")
    if input("Confirm this key belongs to a Free-plan account (type FREE): ").strip() != "FREE":
        raise SystemExit("Nothing saved.")
    key = getpass.getpass("Groq API key (hidden): ").strip()
    if not re.fullmatch(r"gsk_[A-Za-z0-9_-]{20,200}", key):
        raise SystemExit("Key format was not recognized; nothing saved.")
    path = directory / "groq.key"
    if path.exists() and input("Replace the existing project key? (type REPLACE): ").strip() != "REPLACE":
        raise SystemExit("Nothing changed.")
    # Runtime setup protects this directory for the current Windows account.
    # File bytes are plaintext for server use; they remain outside Git/OneDrive.
    with path.open("w", encoding="ascii") as stream:
        stream.write(key)
    key = None
    print("Project key saved outside the checkout. It was not printed or sent anywhere.")
    print("Reload Relay. No backend restart is needed. Generation happens only when you click Explain finding.")


if __name__ == "__main__":
    main()
