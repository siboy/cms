"""Kirim email notifikasi/verifikasi/reset-password lewat SMTP. Best-effort: kalau SMTP tak
dikonfigurasi atau gagal kirim, cukup log & return False -- tidak pernah menggagalkan request API."""
from __future__ import annotations

import smtplib
import ssl
from email.mime.text import MIMEText
from html import escape

from flask import current_app


def send_mail(to: str, subject: str, html: str) -> bool:
    cfg = current_app.config
    host = cfg.get("SMTP_HOST")
    if not host or not to:
        current_app.logger.warning("mailer: SMTP_HOST kosong atau tujuan kosong, lewati kirim ke %r", to)
        return False
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = cfg.get("SMTP_FROM") or cfg.get("SMTP_USER") or "cms@localhost"
    msg["To"] = to
    try:
        port = int(cfg.get("SMTP_PORT", 587))
        cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP          # port 465 = SSL langsung; selain itu STARTTLS bila SMTP_TLS
        kw = {"context": ssl.create_default_context()} if port == 465 else {}
        with cls(host, port, timeout=10, **kw) as s:
            if port != 465 and cfg.get("SMTP_TLS", True):
                s.starttls(context=ssl.create_default_context())
            if cfg.get("SMTP_USER"):
                s.login(cfg["SMTP_USER"], cfg.get("SMTP_PASS", ""))
            s.sendmail(msg["From"], [to], msg.as_string())
        return True
    except Exception as e:                                    # noqa: BLE001
        current_app.logger.error("mailer: gagal kirim ke %s: %s", to, e)
        return False


def notify_account_created(to: str, name: str, username: str, verify_link: str) -> bool:
    html = (f"<p>Halo {name or username},</p>"
            f"<p>Akun CMS kolaborasi kamu (username <b>{username}</b>) sudah dibuat.</p>"
            f"<p>Klik link berikut untuk memverifikasi email ini:<br>"
            f"<a href=\"{verify_link}\">{verify_link}</a></p>")
    return send_mail(to, "Akun CMS kamu dibuat - verifikasi email", html)


def notify_account_activated(to: str, name: str, username: str) -> bool:
    html = (f"<p>Halo {name or username},</p>"
            f"<p>Akun CMS kolaborasi kamu (username <b>{username}</b>) telah diaktifkan oleh admin. "
            f"Kamu sekarang bisa login.</p>")
    return send_mail(to, "Akun CMS kamu diaktifkan", html)


def notify_password_reset(to: str, name: str, username: str, reset_link: str) -> bool:
    html = (f"<p>Halo {name or username},</p>"
            f"<p>Ada permintaan reset password untuk akun CMS (username <b>{username}</b>).</p>"
            f"<p>Klik link berikut untuk mengatur password baru (berlaku 1 jam):<br>"
            f"<a href=\"{reset_link}\">{reset_link}</a></p>"
            f"<p>Kalau kamu tidak minta ini, abaikan saja email ini.</p>")
    return send_mail(to, "Reset password CMS", html)


def notify_pic_assigned(to: str, name: str, actor: str, label: str, link: str) -> bool:
    name, actor, label = escape(name), escape(actor), escape(label)
    html = (f"<p>Halo {name},</p>"
            f"<p><b>{actor}</b> menandaimu sebagai PIC di <b>{label}</b>.</p>"
            f"<p><a href=\"{link}\">Buka di CMS</a></p>")
    return send_mail(to, f"Kamu ditandai PIC — {label}", html)


def notify_comment(to: str, name: str, actor: str, label: str, snippet: str, is_reply: bool, link: str) -> bool:
    name, actor, label, snippet = escape(name), escape(actor), escape(label), escape(snippet)
    verb = "membalas komentarmu" if is_reply else "menulis komentar baru"
    html = (f"<p>Halo {name},</p>"
            f"<p><b>{actor}</b> {verb} di <b>{label}</b>:</p>"
            f"<p style=\"padding:8px 12px;border-left:3px solid #1f6feb;background:#f6f7f9\">{snippet}</p>"
            f"<p><a href=\"{link}\">Buka di CMS</a></p>")
    return send_mail(to, f"Komentar baru — {label}", html)


def notify_company_ready(to: str, name: str, company: str, url: str) -> bool:
    name, company, url = escape(name), escape(company), escape(url)
    html = (f"<p>Halo {name},</p><p>Pembayaran kode perusahaan diterima dan tenant <b>{company}</b> sudah siap:</p>"
            f"<p><a href=\"{url}\">{url}</a></p>"
            f"<p>Masuk memakai email/username dan password akun sdrive Anda. Anda adalah <b>admin pertama</b>: tambah anggota dari menu Admin, "
            f"lalu bayar langganan akun mereka di menu <b>🏢 Perusahaan</b>.</p>")
    return send_mail(to, f"Tenant {company} siap dipakai", html)


def notify_project_invite(to: str, name: str, actor: str, project: str, title: str, link: str) -> bool:
    """Akun yang SUDAH ada diundang masuk tim proyek (jalur 1 maupun jalur 2)."""
    name, actor, project, title = escape(name), escape(actor), escape(project), escape(title)
    html = (f"<p>Halo {name},</p><p><b>{actor}</b> mengundang Anda bergabung di proyek <b>{project}</b> sebagai <b>{title}</b>.</p>"
            f"<p><a href=\"{link}\">Buka sdrive</a></p>")
    return send_mail(to, f"Anda diundang ke proyek {project}", html)


def notify_project_invite_new(to: str, actor: str, project: str, title: str, signup_link: str) -> bool:
    """Alamat email BELUM punya akun: ajak daftar mandiri; begitu akun aktif, otomatis masuk tim proyek."""
    actor, project, title = escape(actor), escape(project), escape(title)
    html = (f"<p>Halo,</p><p><b>{actor}</b> mengundang Anda bergabung di proyek <b>{project}</b> sebagai <b>{title}</b> di sdrive.</p>"
            f"<p>Anda belum punya akun. Daftar dulu memakai <b>email ini</b>, konfirmasi emailnya, dan Anda otomatis masuk ke proyek tersebut:<br>"
            f"<a href=\"{signup_link}\">{signup_link}</a></p>")
    return send_mail(to, f"Undangan proyek {project} — daftar untuk bergabung", html)


def notify_company_invite(to: str, name: str, actor: str, company: str, role: str, username: str, link: str, needs_seat: bool) -> bool:
    """Admin perusahaan menambahkan akun: undangan bergabung + tautan mengatur password (tanpa mengirim password lewat email)."""
    name, actor, company, role, username = escape(name), escape(actor), escape(company), escape(role), escape(username)
    seat = ("<p>Akun Anda aktif setelah admin mengaktifkan langganan akun; Anda baru bisa masuk setelah itu.</p>" if needs_seat else "")
    html = (f"<p>Halo {name},</p><p><b>{actor}</b> mengundang Anda bergabung di <b>{company}</b> sebagai <b>{role}</b>.</p>"
            f"<p>Username Anda: <b>{username}</b>. Atur password Anda lewat tautan berikut (berlaku 7 hari):<br><a href=\"{link}\">{link}</a></p>{seat}")
    return send_mail(to, f"Anda diundang bergabung di {company}", html)
