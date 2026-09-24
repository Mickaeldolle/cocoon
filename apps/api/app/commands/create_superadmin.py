"""Create or promote the only account allowed to access admin endpoints.

Run this command interactively from the private API container. Passwords are read
from the terminal and are never written to source code, environment files or logs.
"""

import argparse
import sys
from getpass import getpass

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.auth.models import User


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or promote a Cocoon superadmin.")
    parser.add_argument("--email", required=True, help="Email address of the administrator.")
    parser.add_argument(
        "--display-name",
        help="Display name. Required only when the account does not already exist.",
    )
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the new account password from standard input instead of prompting.",
    )
    return parser.parse_args()


def read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    return getpass("Mot de passe du nouveau superadmin : ")


def main() -> None:
    args = parse_args()
    try:
        email = validate_email(args.email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as error:
        raise SystemExit(f"Email invalide : {error}") from error

    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.email == email))
        if user is not None:
            user.is_superadmin = True
            session.commit()
            print(f"Le compte existant {email} est désormais superadmin.")
            return

        if not args.display_name or not args.display_name.strip():
            raise SystemExit("--display-name est requis pour un nouveau compte.")
        password = read_password(args.password_stdin)
        if not 12 <= len(password) <= 256:
            raise SystemExit("Le mot de passe doit contenir entre 12 et 256 caractères.")

        user = User(
            email=email,
            display_name=args.display_name.strip(),
            password_hash=hash_password(password),
            is_superadmin=True,
        )
        session.add(user)
        session.commit()
        print(f"Le superadmin {email} a été créé.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
