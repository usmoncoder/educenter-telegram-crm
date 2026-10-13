"""Administrative CLI.

    python -m app.cli create-superadmin --username admin [--full-name "Ism Familiya"]
    python -m app.cli reset-password --username admin

Passwords are read interactively (not echoed, never accepted as command-line arguments so they
do not end up in shell history or `ps`). For unattended provisioning, the password can be piped
on stdin with --password-stdin.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

import sqlalchemy as sa

from app.core.config import get_settings
from app.core.security import hash_password, password_problems
from app.core.timeutil import utcnow
from app.db.enums import Role
from app.db.models import Admin, AuditEvent
from app.db.session import create_engine, create_session_factory, transaction
from app.services.auth import revoke_all_sessions


def _read_password(username: str, from_stdin: bool) -> str:
    if from_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("Yangi parol: ")
        if getpass.getpass("Parolni takrorlang: ") != password:
            raise SystemExit("XATO: parollar mos kelmadi")
    problems = password_problems(password, username)
    if problems:
        raise SystemExit("XATO: " + "; ".join(problems))
    return password


async def create_superadmin(username: str, full_name: str, from_stdin: bool, allow_additional: bool) -> None:
    username = username.strip().lower()
    engine = create_engine(get_settings())
    factory = create_session_factory(engine)
    try:
        async with transaction(factory) as s:
            existing_super = await s.scalar(
                sa.select(sa.func.count()).select_from(Admin).where(Admin.role == Role.SUPER_ADMIN)
            )
            if existing_super and not allow_additional:
                raise SystemExit(
                    "Super Admin allaqachon mavjud. Qo'shimcha administratorlarni veb-paneldan yarating "
                    "(yoki --allow-additional bayrog'idan foydalaning)."
                )
            if await s.scalar(sa.select(Admin.id).where(Admin.username == username)):
                raise SystemExit("XATO: bu login band")
            password = _read_password(username, from_stdin)
            admin = Admin(
                username=username,
                full_name=full_name,
                role=Role.SUPER_ADMIN,
                password_hash=hash_password(password),
                password_changed_at=utcnow(),
            )
            s.add(admin)
            await s.flush()
            s.add(
                AuditEvent(
                    action="admin.bootstrap",
                    actor_username="cli",
                    entity_type="admin",
                    entity_id=str(admin.id),
                    details={"username": username},
                )
            )
        print(f"Super Admin yaratildi: {username}")
    finally:
        await engine.dispose()


async def reset_password(username: str, from_stdin: bool) -> None:
    username = username.strip().lower()
    engine = create_engine(get_settings())
    factory = create_session_factory(engine)
    try:
        async with transaction(factory) as s:
            admin = await s.scalar(sa.select(Admin).where(Admin.username == username))
            if admin is None:
                raise SystemExit("XATO: bunday administrator yo'q")
            admin.password_hash = hash_password(_read_password(username, from_stdin))
            admin.password_changed_at = utcnow()
            admin.is_active = True
            s.add(
                AuditEvent(
                    action="admin.reset_password_cli",
                    actor_username="cli",
                    entity_type="admin",
                    entity_id=str(admin.id),
                )
            )
            await revoke_all_sessions(s, admin.id)
        print(f"Parol yangilandi: {username}")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("create-superadmin", help="birinchi Super Admin'ni yaratish")
    p1.add_argument("--username", required=True)
    p1.add_argument("--full-name", default="")
    p1.add_argument("--password-stdin", action="store_true")
    p1.add_argument("--allow-additional", action="store_true")
    p2 = sub.add_parser("reset-password", help="administrator parolini tiklash")
    p2.add_argument("--username", required=True)
    p2.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args()
    if args.cmd == "create-superadmin":
        asyncio.run(create_superadmin(args.username, args.full_name, args.password_stdin, args.allow_additional))
    else:
        asyncio.run(reset_password(args.username, args.password_stdin))


if __name__ == "__main__":
    main()
