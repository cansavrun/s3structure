"""Yalnızca yerel S3 taklidi için örnek veriler. Gerçek AWS'ye veri yazmayı reddeder."""

import json
from urllib.parse import urlsplit

import boto3

from app.core.config import Settings
from app.core.database import make_database
from app.model import Customer
from app.services.admin import AdminService


def main():
    settings = Settings()
    endpoint = settings.s3_endpoint_url or ""
    if (
        settings.environment != "development"
        or settings.s3_mode != "local"
        or urlsplit(endpoint).hostname not in {"localhost", "127.0.0.1", "s3"}
    ):
        raise SystemExit("Demo yalnızca development + yerel S3 endpoint ile çalışır")
    client = boto3.client("s3", endpoint_url=endpoint, region_name="us-east-1")
    bucket = "tenantfiles-demo"
    if bucket not in [b["Name"] for b in client.list_buckets()["Buckets"]]:
        client.create_bucket(Bucket=bucket)
    engine, factory = make_database(settings.database_url.get_secret_value())
    output = []
    for cid, name in [("amy_c001", "Amy Energy"), ("atlas_c002", "Atlas Labs")]:
        with factory.begin() as db:
            if db.get(Customer, cid) is None:
                AdminService(db).add_customer(
                    customer_id=cid, name=name, bucket=bucket, prefix=cid + "/"
                )
            key, raw = AdminService(db).issue_key(
                settings.app_secret.get_secret_value(), cid, "Yerel demo", 7
            )
            output.append({"customer": cid, "api_key": raw, "key_id": key.id})
        for month in ["07", "08", "09"]:
            for site in ["berlin_solar", "hamburg_wind"]:
                prefix = f"{cid}/2026/{month}/{site}/"
                client.put_object(
                    Bucket=bucket,
                    Key=prefix + "production.csv",
                    Body=(
                        "date,site,energy_kwh,availability_pct\n"
                        + "".join(
                            f"2026-{month}-{day:02d},{site},{1240 + day * 37},99.8\n"
                            for day in range(1, 29)
                        )
                    ).encode(),
                    ContentType="text/csv",
                )
                client.put_object(
                    Bucket=bucket,
                    Key=prefix + "summary.csv",
                    Body=b"metric,value,unit\nproduction,48260,kWh\navailability,99.8,%\n",
                    ContentType="text/csv",
                )
                client.put_object(
                    Bucket=bucket,
                    Key=prefix + "readme.txt",
                    Body=f"{name} - {site} monthly export.\n".encode(),
                )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    client.close()
    engine.dispose()


if __name__ == "__main__":
    main()
