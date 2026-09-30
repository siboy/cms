import os
from datetime import timedelta


class Config:
    DB_HOST = os.environ.get("CMS_DB_HOST", "cms-mysql")
    DB_PORT = int(os.environ.get("CMS_DB_PORT", 3306))
    DB_USER = os.environ.get("CMS_DB_USER", "cms")
    DB_PASS = os.environ.get("CMS_DB_PASS", "")
    DB_NAME = os.environ.get("CMS_DB_NAME", "cms")
    DB_POOL = int(os.environ.get("CMS_DB_POOL", 12))                 # per proses worker web
    REDIS_URL = os.environ.get("CMS_REDIS_URL", "redis://cms-redis:6379/0")
    SECRET_KEY = os.environ.get("CMS_SECRET_KEY", "")
    UPLOAD_MAX_MB = int(os.environ.get("CMS_UPLOAD_MAX_MB", 20))
    DATA_DIR = os.environ.get("CMS_DATA_DIR", "/data")

    # flask
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("CMS_COOKIE_SECURE", "0") == "1"      # 1 bila di belakang HTTPS
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get("CMS_SESSION_HOURS", 12)))
    JSON_AS_ASCII = False
