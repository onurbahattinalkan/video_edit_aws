"""AWS altyapi otomasyon betigi.

Bu betik, video_stream_app projesinin ihtiyac duydugu AWS kaynaklarini
(Kinesis Video Stream + RDS PostgreSQL) idempotent bir sekilde olusturur,
.env dosyasini guncel DATABASE_URL ile senkronlar, Alembic migrasyonlarini
uygular ve son olarak uygulamayi (uvicorn) baslatir.

Kullanim:
    python setup_infra.py
"""

from __future__ import annotations

import logging
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
ENV_PATH = ROOT_DIR / ".env"
ENV_EXAMPLE_PATH = ROOT_DIR / ".env.example"

RDS_INSTANCE_ID = "video-stream-db-instance"
RDS_DB_NAME = "video_stream_db"
RDS_MASTER_USERNAME = "postgres"
RDS_PORT = 5432

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("setup_infra")


class InfraSetupError(RuntimeError):
    """Otomasyon akisinda kurtarilamayan bir hata olustugunda firlatilir."""


def load_environment() -> None:
    """`.env` yoksa `.env.example`'dan olusturur, ardindan ortami yukler."""
    if not ENV_PATH.exists():
        if ENV_EXAMPLE_PATH.exists():
            ENV_PATH.write_text(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            logger.info(".env bulunamadi, .env.example baz alinarak olusturuldu.")
        else:
            raise InfraSetupError(".env ve .env.example dosyalarinin hicbiri bulunamadi.")
    load_dotenv(ENV_PATH)

    placeholder_values = {"your_access_key_id", "your_secret_access_key", ""}
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        if os.environ.get(key) in placeholder_values:
            os.environ.pop(key, None)


def get_boto_clients() -> tuple["boto3.client", "boto3.client"]:
    """RDS ve Kinesis Video kontrol-plane istemcilerini kimlik dogrulamasiyla baslatir."""
    region = os.getenv("AWS_REGION", "eu-central-1")
    kwargs: dict[str, str] = {"region_name": region}

    placeholder_values = {"your_access_key_id", "your_secret_access_key", ""}
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    if access_key in placeholder_values or secret_key in placeholder_values:
        access_key, secret_key = None, None
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key

    try:
        rds_client = boto3.client("rds", **kwargs)
        kvs_client = boto3.client("kinesisvideo", **kwargs)
        rds_client.describe_db_instances(MaxRecords=20)
    except (BotoCoreError, ClientError) as exc:
        raise InfraSetupError(f"AWS kimlik dogrulama / baglanti hatasi: {exc}") from exc

    logger.info("AWS kimlik dogrulama basarili (region=%s).", region)
    return rds_client, kvs_client


def ensure_kinesis_stream(kvs_client) -> str:
    """KVS stream'inin var oldugunu garanti eder, ARN dondurur."""
    stream_name = os.getenv("KVS_STREAM_NAME", "demo-video-stream")

    try:
        response = kvs_client.describe_stream(StreamName=stream_name)
        arn = response["StreamInfo"]["StreamARN"]
        logger.info("Kinesis Video Stream zaten mevcut: %s (%s)", stream_name, arn)
        return arn
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
            raise InfraSetupError(f"Kinesis stream sorgulama hatasi: {exc}") from exc

    logger.info("Kinesis Video Stream bulunamadi, olusturuluyor: %s", stream_name)
    try:
        create_response = kvs_client.create_stream(
            StreamName=stream_name,
            DataRetentionInHours=24,
            MediaType="video/h264",
        )
    except ClientError as exc:
        raise InfraSetupError(f"Kinesis stream olusturma hatasi: {exc}") from exc

    arn = create_response["StreamARN"]
    logger.info("Kinesis Video Stream olusturuldu: %s", arn)
    return arn


def ensure_rds_instance(rds_client) -> tuple[str, str]:
    """RDS PostgreSQL instance'ini garanti eder, (endpoint, master_password) dondurur."""
    master_password = os.getenv("RDS_MASTER_PASSWORD")

    try:
        describe_response = rds_client.describe_db_instances(DBInstanceIdentifier=RDS_INSTANCE_ID)
        instance = describe_response["DBInstances"][0]
        logger.info("RDS instance zaten mevcut: %s (durum=%s)", RDS_INSTANCE_ID, instance["DBInstanceStatus"])
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "DBInstanceNotFound":
            raise InfraSetupError(f"RDS instance sorgulama hatasi: {exc}") from exc

        if not master_password:
            master_password = secrets.token_urlsafe(18).replace("/", "_").replace("=", "")
            _persist_env_value("RDS_MASTER_PASSWORD", master_password)
            logger.info("RDS master sifresi uretildi ve .env'e kaydedildi.")

        logger.info("RDS instance bulunamadi, olusturuluyor: %s", RDS_INSTANCE_ID)
        try:
            rds_client.create_db_instance(
                DBInstanceIdentifier=RDS_INSTANCE_ID,
                DBName=RDS_DB_NAME,
                Engine="postgres",
                DBInstanceClass="db.t3.micro",
                MasterUsername=RDS_MASTER_USERNAME,
                MasterUserPassword=master_password,
                AllocatedStorage=20,
                StorageType="gp2",
                PubliclyAccessible=True,
                BackupRetentionPeriod=1,
            )
        except ClientError as create_exc:
            raise InfraSetupError(f"RDS instance olusturma hatasi: {create_exc}") from create_exc

        instance = _wait_for_rds_available(rds_client)
    else:
        if instance["DBInstanceStatus"] != "available":
            instance = _wait_for_rds_available(rds_client)
        if not master_password:
            raise InfraSetupError(
                "RDS instance mevcut ama RDS_MASTER_PASSWORD .env icinde tanimli degil. "
                "DATABASE_URL'i manuel guncellemeniz gerekebilir."
            )

    endpoint = instance["Endpoint"]["Address"]
    logger.info("RDS instance hazir, endpoint: %s", endpoint)
    return endpoint, master_password


def _wait_for_rds_available(rds_client, poll_seconds: int = 20):
    """RDS instance'i 'available' durumuna gelene kadar bekler."""
    logger.info("RDS instance'inin 'available' durumuna gelmesi bekleniyor (her %ss kontrol)...", poll_seconds)
    waiter = rds_client.get_waiter("db_instance_available")
    try:
        waiter.wait(
            DBInstanceIdentifier=RDS_INSTANCE_ID,
            WaiterConfig={"Delay": poll_seconds, "MaxAttempts": 60},
        )
    except (BotoCoreError, ClientError) as exc:
        raise InfraSetupError(f"RDS instance bekleme hatasi: {exc}") from exc

    response = rds_client.describe_db_instances(DBInstanceIdentifier=RDS_INSTANCE_ID)
    instance = response["DBInstances"][0]
    logger.info("RDS instance 'available' durumuna geldi.")
    return instance


def _persist_env_value(key: str, value: str) -> None:
    """`.env` dosyasindaki bir key=value satirini gunceller, yoksa ekler."""
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    prefix = f"{key}="
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = f"{prefix}{value}"
            updated = True
            break
    if not updated:
        lines.append(f"{prefix}{value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value


def update_database_url(endpoint: str, password: str) -> None:
    """DATABASE_URL'i RDS endpoint'i ile gunceller ve .env'e yazar."""
    database_url = (
        f"postgresql+psycopg2://{RDS_MASTER_USERNAME}:{password}@{endpoint}:{RDS_PORT}"
        f"/{RDS_DB_NAME}?sslmode=require"
    )
    _persist_env_value("DATABASE_URL", database_url)
    logger.info("DATABASE_URL .env icinde guncellendi (endpoint=%s).", endpoint)


def run_alembic_migrations() -> None:
    """`alembic upgrade head` komutunu calistirir."""
    logger.info("Alembic migrasyonlari uygulaniyor...")
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT_DIR,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise InfraSetupError(f"Alembic migrasyon hatasi: {exc}") from exc
    logger.info("Alembic migrasyonlari basariyla tamamlandi.")


def start_application() -> subprocess.Popen:
    """uvicorn sunucusunu arka planda baslatir."""
    logger.info("Uygulama (uvicorn) arka planda baslatiliyor...")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
        cwd=ROOT_DIR,
    )
    logger.info("Uvicorn baslatildi (pid=%s). http://0.0.0.0:8000/docs adresinden Swagger'a erisilebilir.", process.pid)
    return process


def main() -> None:
    try:
        load_environment()
        rds_client, kvs_client = get_boto_clients()
        ensure_kinesis_stream(kvs_client)
        endpoint, password = ensure_rds_instance(rds_client)
        update_database_url(endpoint, password)
        run_alembic_migrations()
        start_application()
    except InfraSetupError as exc:
        logger.error("Kurulum basarisiz: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
