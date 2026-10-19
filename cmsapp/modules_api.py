"""Penegakan modul fitur berlangganan (utils/modules.py) di sisi server + GET /api/modules untuk UI.
Pengguna tenant TIDAK bisa mengaktifkan modul -- hanya operator lewat cmspanel (env CMS_MODULES di .env tenant)."""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, jsonify

from cmsapp import auth
from utils import modules as mods

bp = Blueprint("modules", __name__, url_prefix="/api")


def locked_response(key: str):
    return jsonify(error=mods.locked_message(key), code="module_locked", module=key, label=mods.LABEL.get(key, key)), 403


def guard(key: str):
    """Dekorator rute: tolak 403 {code: module_locked} bila modul `key` tidak aktif di tenant ini."""
    def deco(fn):
        @wraps(fn)
        def inner(*a, **kw):
            if not mods.is_on(key):
                return locked_response(key)
            return fn(*a, **kw)
        return inner
    return deco


@bp.get("/modules")
@auth.require()
def modules_state():
    on = mods.enabled()
    return jsonify(modules=[{"key": m["key"], "label": m["label"], "group": m["group"], "on": m["key"] in on} for m in mods.MODULES],
                   category_module=mods.CATEGORY_MODULE, sim_module=mods.SIM_MODULE, tool_module=mods.TOOL_MODULE)
