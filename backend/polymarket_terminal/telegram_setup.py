import os
import sys

import httpx

from polymarket_terminal.envfile import ENV_PATH, load_env, set_env_value


def main() -> None:
    load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit(f"Add TELEGRAM_BOT_TOKEN=... to {ENV_PATH} first.")
    updates = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
    if updates.status_code == 401:
        sys.exit("Telegram rejected the token. Check TELEGRAM_BOT_TOKEN in backend/.env.")
    updates.raise_for_status()
    chats = {}
    for update in updates.json().get("result", []):
        chat = (update.get("message") or update.get("channel_post") or {}).get("chat")
        if chat:
            chats[str(chat["id"])] = chat.get("username") or chat.get("title") or chat.get("first_name")
    if not chats:
        sys.exit("No messages found. Open your bot in Telegram, send it any message, then run this again.")
    if len(chats) > 1:
        for chat_id, name in chats.items():
            print(f"{chat_id}  {name}")
        sys.exit("Several chats found. Add the right one as TELEGRAM_CHAT_ID=... in backend/.env.")
    chat_id, name = next(iter(chats.items()))
    set_env_value("TELEGRAM_CHAT_ID", chat_id)
    httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": "Polymarket terminal alerts are set up."},
        timeout=20,
    ).raise_for_status()
    print(f"Saved chat {chat_id} ({name}) to backend/.env and sent a test message.")


if __name__ == "__main__":
    main()
