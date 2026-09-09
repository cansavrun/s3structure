"""Operatör giriş noktası; argümanları servise çevirir ve transaction'ı yönetir."""

import argparse
import json

from app.core.config import Settings
from app.core.database import make_database
from app.services.admin import AdminService


def main():
    parser = argparse.ArgumentParser(description="TenantFiles yönetimi")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add-customer")
    add.add_argument("--id", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--bucket", required=True)
    add.add_argument(
        "--prefix", required=True, help="Örn: amy_c001/; özel bucket kökü için boş string"
    )
    add.add_argument("--role-arn")
    add.add_argument("--external-id")
    add.add_argument("--kms-key-arn")
    issue = commands.add_parser("issue-key")
    issue.add_argument("--customer", required=True)
    issue.add_argument("--name", required=True, help="Kişi veya entegrasyon adı")
    issue.add_argument("--days", type=int, default=90)
    revoke = commands.add_parser("revoke-key")
    revoke.add_argument("--id", required=True)
    disable = commands.add_parser("disable-customer")
    disable.add_argument("--id", required=True)
    commands.add_parser("list-customers")
    keys = commands.add_parser("list-keys")
    keys.add_argument("--customer", required=True)
    args = parser.parse_args()
    settings = Settings()
    engine, factory = make_database(settings.database_url.get_secret_value())
    try:
        with factory.begin() as db:
            service = AdminService(db)
            if args.command == "add-customer":
                if settings.s3_mode == "sts" and (not args.role_arn or not args.external_id):
                    raise ValueError("STS modunda --role-arn ve --external-id zorunlu")
                customer = service.add_customer(
                    customer_id=args.id,
                    name=args.name,
                    bucket=args.bucket,
                    prefix=args.prefix,
                    role_arn=args.role_arn,
                    external_id=args.external_id,
                    kms_key_arn=args.kms_key_arn,
                )
                output = {"id": customer.id, "created": True}
            elif args.command == "issue-key":
                key, raw = service.issue_key(
                    settings.app_secret.get_secret_value(), args.customer, args.name, args.days
                )
                output = {
                    "key_id": key.id,
                    "api_key": raw,
                    "note": "Yalnızca bir kez gösterilir. Güvenli kanaldan paylaşın.",
                }
            elif args.command == "revoke-key":
                output = {"revoked": service.revoke_key(args.id).id}
            elif args.command == "disable-customer":
                output = {"disabled": service.disable_customer(args.id).id}
            elif args.command == "list-customers":
                output = service.list_customers()
            else:
                output = service.list_keys(args.customer)
            if args.command not in {"list-customers", "list-keys"}:
                service.record_action(args.command, getattr(args, "customer", None))
        # Commit tamamlanmadan anahtarı göstermiyoruz.
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except ValueError as exc:
        parser.exit(2, f"Hata: {exc}\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
