"""One-time interactive Telegram login.

    python -m app.telegram.auth_cli            # log in (or verify an existing session)
    python -m app.telegram.auth_cli --logout   # terminate the session on Telegram and delete it

The verification code and the two-step password are read from the terminal (the password
with getpass, never echoed), passed directly to Telegram and never stored or logged.
Stop the worker before running this command: two processes must not use one session file.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from telethon import errors as te

from app.core.config import get_settings
from app.telegram.client import build_client, secure_session_file, session_file_exists


def _ask_code() -> str:
    return input("Telegram yuborgan tasdiqlash kodini kiriting: ").strip()


def _ask_password() -> str:
    return getpass.getpass("Ikki bosqichli tekshiruv (2FA) parolini kiriting: ")


async def login() -> int:
    settings = get_settings()
    if not settings.telegram_configured:
        print("XATO: .env faylida TELEGRAM_API_ID va TELEGRAM_API_HASH ko'rsatilmagan.", file=sys.stderr)
        return 2
    client = build_client(settings, catch_up=False)
    await client.connect()
    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"Sessiya allaqachon faol: {me.first_name or ''} (@{me.username or '-'}, ID {me.id}).")
            return 0
        phone = settings.telegram_phone or (await asyncio.to_thread(input, "Telefon raqam (+998...): ")).strip()
        try:
            await client.start(phone=phone, code_callback=_ask_code, password=_ask_password, max_attempts=3)
        except te.PhoneNumberInvalidError:
            print("XATO: telefon raqam noto'g'ri.", file=sys.stderr)
            return 1
        except (te.PhoneCodeInvalidError, te.PhoneCodeExpiredError):
            print("XATO: tasdiqlash kodi noto'g'ri yoki muddati o'tgan.", file=sys.stderr)
            return 1
        except te.PasswordHashInvalidError:
            print("XATO: 2FA paroli noto'g'ri.", file=sys.stderr)
            return 1
        except te.FloodWaitError as exc:
            print(f"XATO: Telegram {exc.seconds} soniya kutishni talab qilmoqda.", file=sys.stderr)
            return 1
        except RuntimeError as exc:  # raised by start() after max_attempts
            print(f"XATO: {exc}", file=sys.stderr)
            return 1
        me = await client.get_me()
        print(f"Muvaffaqiyatli kirildi: {me.first_name or ''} (@{me.username or '-'}, ID {me.id}).")
        print(f"Sessiya fayli: {settings.session_path}.session (maxfiy saqlang!)")
        return 0
    finally:
        await client.disconnect()
        secure_session_file(settings)


async def logout() -> int:
    settings = get_settings()
    if not session_file_exists(settings):
        print("Sessiya fayli topilmadi.")
        return 0
    client = build_client(settings, catch_up=False)
    await client.connect()
    try:
        if await client.is_user_authorized():
            await client.log_out()  # also deletes the session file
            print("Sessiya Telegramda yakunlandi va o'chirildi.")
        else:
            print("Sessiya allaqachon yaroqsiz.")
    finally:
        if client.is_connected():
            await client.disconnect()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="EduCenter CRM - Telegram akkauntiga kirish")
    parser.add_argument("--logout", action="store_true", help="sessiyani yakunlash va o'chirish")
    args = parser.parse_args()
    sys.exit(asyncio.run(logout() if args.logout else login()))


if __name__ == "__main__":
    main()
