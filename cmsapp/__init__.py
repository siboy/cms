"""Aplikasi CMS kolaborasi:  gunicorn -k gevent 'cmsapp:create_app()'"""
import os

from flask import Flask, jsonify, send_from_directory

from cmsapp.config import Config
from cmsapp.realtime import Hub, RedisLocks, make_redis
from utils import blockstore


def create_app(cfg=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(cfg)
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("CMS_SECRET_KEY wajib diisi")
    app.config["MAX_CONTENT_LENGTH"] = app.config["UPLOAD_MAX_MB"] * 1024 * 1024

    r = make_redis(app.config["REDIS_URL"])
    locks = RedisLocks(r)
    app.extensions["cms_redis"] = r
    app.extensions["cms_locks"] = locks
    app.extensions["cms_hub"] = Hub(app.config["REDIS_URL"])
    app.extensions["cms_store"] = blockstore.open_mysql(
        app.config["DB_HOST"], app.config["DB_USER"], app.config["DB_PASS"], app.config["DB_NAME"],
        app.config["DB_PORT"], pool_size=app.config["DB_POOL"], locks=locks)

    from cmsapp.api import bp
    app.register_blueprint(bp)

    @app.get("/")
    def ui():
        return send_from_directory(os.path.join(os.path.dirname(__file__), "ui"), "index.html")

    @app.get("/health")
    def health():
        try:
            r.ping()
            app.extensions["cms_store"].list_documents()
            return jsonify(ok=True)
        except Exception as e:                      # noqa: BLE001
            return jsonify(ok=False, error=str(e)[:200]), 503

    return app
