#!/usr/bin/env python3
"""Utility script to reset, clear, create, or promote admin accounts in ForgeMind."""

import argparse
import sys

from app import create_app
from extensions import db
from models import AccountStatus, Role, User


def main():
    parser = argparse.ArgumentParser(description="ForgeMind Admin Account Management Utility")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete all existing ADMIN accounts from the database.",
    )
    parser.add_argument(
        "--email",
        type=str,
        default="admin@forgemind.local",
        help="Email address of the admin account (default: admin@forgemind.local)",
    )
    parser.add_argument(
        "--password",
        type=str,
        default=None,
        help="New password for the admin account. If omitted, defaults to 'Admin123!'.",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="Plant Admin",
        help="Display name for newly created admin account (default: 'Plant Admin')",
    )
    parser.add_argument(
        "--promote",
        type=str,
        metavar="USER_EMAIL",
        help="Promote an existing user to ADMIN and set their status to APPROVED.",
    )

    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        # Option 1: Promote existing user
        if args.promote:
            target_email = args.promote.strip().lower()
            user = User.query.filter_by(email=target_email).first()
            if not user:
                print(f"[!] User with email '{target_email}' not found.", file=sys.stderr)
                sys.exit(1)
            user.role = Role.ADMIN.value
            user.status = AccountStatus.APPROVED.value
            db.session.commit()
            print(f"[✓] Successfully promoted '{user.email}' ({user.name}) to ADMIN with status APPROVED.")
            return

        # Option 2: Clear all admin accounts
        if args.clear:
            admins = User.query.filter(User.role.ilike("admin")).all()
            if not admins:
                print("[-] No ADMIN accounts found to delete.")
                return
            count = len(admins)
            for a in admins:
                print(f"  [-] Deleting admin: {a.email} ({a.name})")
                db.session.delete(a)
            db.session.commit()
            print(f"[✓] Successfully cleared {count} ADMIN account(s).")
            return

        # Option 3: Reset or create the admin account
        target_email = args.email.strip().lower()
        password = args.password if args.password else "Admin123!"

        user = User.query.filter_by(email=target_email).first()
        if user:
            user.set_password(password)
            user.role = Role.ADMIN.value
            user.status = AccountStatus.APPROVED.value
            db.session.commit()
            print(f"[✓] Admin account '{user.email}' updated successfully.")
            print(f"    - Role: ADMIN")
            print(f"    - Status: APPROVED")
            print(f"    - Password has been reset to: '{password}'")
        else:
            new_user = User(
                name=args.name,
                email=target_email,
                role=Role.ADMIN.value,
                status=AccountStatus.APPROVED.value,
                auth_provider="manual",
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            print(f"[✓] Created new ADMIN account '{new_user.email}'.")
            print(f"    - Role: ADMIN")
            print(f"    - Status: APPROVED")
            print(f"    - Password: '{password}'")


if __name__ == "__main__":
    main()
