"""Explicit, bounded Meta adapters. No network on import or construction.

Initial support: one public HTTPS JPEG with a reviewed caption, Facebook Page
or Instagram professional account using Instagram Login. No personal Facebook
profiles, carousel posts, Reels, Stories or OAuth setup. Caller owns persistent
confirmation, dispatch locking and receipts; never retry an unknown dispatch.

Primary contracts consulted 2026-09-06:
https://developers.facebook.com/docs/pages-api/posts/
https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
from collections.abc import Mapping
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class MetaTransportError(Exception):
    """Only numeric HTTP status may escape this boundary; never raw API bodies."""

    def __init__(self, status_code=0):
        self.status_code = int(status_code)
        super().__init__("Meta request failed")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrllibMetaTransport:
    """No redirects, automatic retries or secrets in query strings."""

    def request(self, method, url, *, headers, data=None, timeout=15):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {"graph.facebook.com", "graph.instagram.com"} or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise MetaTransportError()
        body = urlencode(data).encode("utf-8") if data is not None else None
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with build_opener(_NoRedirect).open(request, timeout=min(max(float(timeout), 1), 20)) as response:
                raw = response.read(1_048_577)
                if len(raw) > 1_048_576:
                    raise MetaTransportError()
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise MetaTransportError()
                return payload
        except HTTPError as exc:
            # Do not parse, propagate, log or save the body: it can echo tokens.
            status = exc.code
            exc.close()
            raise MetaTransportError(status) from None
        except (URLError, TimeoutError, socket.timeout, OSError, ValueError, HTTPException):
            raise MetaTransportError() from None


def is_public_https_url(value):
    """Syntactic public DNS URL guard; no fetching or DNS lookup during preview.

    This does not prove availability. Media is fetched by Meta, never this app.
    IP literals and local naming conventions are deliberately unsupported.
    """
    if not isinstance(value, str) or len(value) > 4096 or any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
        return False
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.fragment:
            return False
        if any(key.lower() in {"access_token", "token", "api_key", "apikey", "authorization", "password", "secret"} for key, _ in parse_qsl(parsed.query)):
            return False
        if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host):
            return False
        if any(not label or label.startswith("-") or label.endswith("-") for label in host.split(".")):
            return False
        if host.endswith((".localhost", ".local", ".internal", ".lan", ".home", ".test", ".invalid")) or host.rsplit(".", 1)[-1].isdigit():
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            return True
    except (ValueError, TypeError):
        return False


def _graph_id(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9]{1,40}", value) is not None


class _MetaAdapter:
    channel = ""
    graph_host = ""
    account_key = ""
    token_key = ""

    def __init__(self, env=None, transport=None):
        source = os.environ if env is None else env
        self.account_id = str(source.get(self.account_key, "")).strip()
        self.version = str(source.get("SCENA_META_API_VERSION", "")).strip()
        self._token = str(source.get(self.token_key, "")).strip()
        self._transport = transport if transport is not None else UrllibMetaTransport()

    @property
    def configured(self):
        return bool(_graph_id(self.account_id) and re.fullmatch(r"v[1-9][0-9]{0,2}\.0", self.version) and self._token and not any(c.isspace() or ord(c) < 32 for c in self._token))

    def configuration_status(self):
        fingerprint = hashlib.sha256(json.dumps([self.channel, self.account_id, self.version, self._token], separators=(",", ":")).encode()).hexdigest()
        return {"channel": self.channel, "account_id": self.account_id if _graph_id(self.account_id) else "", "configured": self.configured, "fingerprint": fingerprint, "api_version": self.version if re.fullmatch(r"v[1-9][0-9]{0,2}\.0", self.version) else "", "supported_formats": ["single_jpeg"], "verified": False}

    def _result(self, status, **fields):
        return {"status": status, "channel": self.channel, "account_id": self.account_id if _graph_id(self.account_id) else "", "configuration_fingerprint": self.configuration_status()["fingerprint"], "external_id": "", "url": "", "container_id": "", "publish_attempted": False, **fields}

    def _fail(self, code, message):
        return self._result("failed", error_code=code, message=message)

    def _validate(self, snapshot):
        if not self.configured:
            return self._fail("not_configured", "Подключение не настроено. Обратитесь к оператору SCENA.")
        if not isinstance(snapshot, Mapping) or snapshot.get("channel") != self.channel or str(snapshot.get("account_id", "")) != self.account_id:
            return self._fail("account_mismatch", "Аккаунт изменился. Подготовьте новый просмотр публикации.")
        if snapshot.get("configuration_fingerprint") and snapshot["configuration_fingerprint"] != self.configuration_status()["fingerprint"]:
            return self._fail("configuration_changed", "Подключение изменилось. Подготовьте новый просмотр публикации.")
        if snapshot.get("status") in {"sent", "unknown", "processing", "sending"}:
            return self._fail("already_dispatched", "У отправки уже есть результат. Повторная публикация заблокирована.")
        if snapshot.get("media_type", "image") not in {"image", "IMAGE", "single_image", "single_jpeg"} or any(snapshot.get(k) for k in ("video_url", "children", "media_urls", "image_urls")):
            return self._fail("unsupported_format", "В этой версии поддерживается одна фотография JPEG с подписью.")
        image_url = snapshot.get("image_url", "")
        if not is_public_https_url(image_url) or not urlsplit(image_url).path.lower().endswith((".jpg", ".jpeg")):
            return self._fail("invalid_image_url", "Нужна общедоступная HTTPS-ссылка на подготовленную фотографию JPEG.")
        if not is_public_https_url(snapshot.get("return_url", "")):
            return self._fail("invalid_return_url", "Ссылка на публикацию SCENA должна быть доступна по HTTPS.")
        caption = snapshot.get("caption")
        if not isinstance(caption, str) or not caption.strip() or len(caption) > 2200:
            return self._fail("invalid_caption", "Подпись должна содержать от 1 до 2200 символов.")
        return None

    def _request(self, method, path, data=None, fields=None):
        url = f"https://{self.graph_host}/{self.version}/{path}"
        if fields:
            url += "?" + urlencode({"fields": fields})
        response = self._transport.request(method, url, headers={"Authorization": "Bearer " + self._token, "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}, data=data, timeout=15)
        if not isinstance(response, dict):
            raise MetaTransportError()
        if "error" in response:
            raise MetaTransportError(400)
        return response

    def _request_failure(self, exc, *, mutating=False, **fields):
        # Known Graph 4xx rejection is failure; timeout/5xx is indeterminate.
        code = exc.status_code if isinstance(exc, MetaTransportError) else 0
        unknown = mutating and not 400 <= code < 500
        return self._result("unknown" if unknown else "failed", error_code="outcome_unknown" if unknown else "meta_rejected", message="Результат отправки неизвестен. Проверьте площадку перед дальнейшими действиями." if unknown else "Площадка не подтвердила запрос. Проверьте подключение и разрешения.", **fields)

    def verify_account(self):
        """Read token owner only; explicit UI action, not proof of app review.

        Instagram Login uses user_id as documented by Meta Get Started. A
        successful read verifies identity, not every publishing permission.
        """
        status = self.configuration_status()
        if not self.configured:
            return {**status, "error_code": "not_configured", "message": "Подключение не настроено."}
        fields = "id,name" if self.channel == "facebook" else "user_id,username"
        try:
            payload = self._request("GET", "me", fields=fields)
        except (MetaTransportError, TimeoutError, OSError):
            return {**status, "error_code": "verification_failed", "message": "Не удалось проверить аккаунт. Проверьте подключение и разрешения."}
        actual = str(payload.get("id" if self.channel == "facebook" else "user_id", ""))
        if actual != self.account_id:
            return {**status, "error_code": "account_mismatch", "message": "Токен относится к другому аккаунту. Обратитесь к оператору SCENA."}
        name = str(payload.get("name" if self.channel == "facebook" else "username", ""))
        name = name.replace(self._token, "[redacted]")
        name = "".join(c for c in name if ord(c) >= 32)[:120]
        return {**status, "verified": True, "display_name": name, "publishing_permissions_verified": False, "message": "Аккаунт подтверждён. Права на публикацию проверяются площадкой при отправке."}


class FacebookPagesAdapter(_MetaAdapter):
    channel = "facebook"
    graph_host = "graph.facebook.com"
    account_key = "SCENA_FACEBOOK_PAGE_ID"
    token_key = "SCENA_FACEBOOK_PAGE_TOKEN"

    def publish(self, snapshot):
        problem = self._validate(snapshot)
        if problem:
            return problem
        try:
            payload = self._request("POST", f"{self.account_id}/photos", data={"url": snapshot["image_url"], "caption": snapshot["caption"], "published": "true"})
        except (MetaTransportError, TimeoutError, OSError) as exc:
            return self._request_failure(exc, mutating=True, publish_attempted=True)
        post_id = str(payload.get("post_id", ""))
        if not re.fullmatch(r"[0-9]{1,40}_[0-9]{1,40}", post_id) or post_id.split("_", 1)[0] != self.account_id:
            return self._result("unknown", error_code="missing_receipt", message="Площадка ответила без идентификатора публикации. Проверьте страницу Facebook.", publish_attempted=True)
        return self._result("sent", external_id=post_id, url="https://www.facebook.com/" + post_id, publish_attempted=True)


class InstagramAdapter(_MetaAdapter):
    channel = "instagram"
    graph_host = "graph.instagram.com"
    account_key = "SCENA_INSTAGRAM_ACCOUNT_ID"
    token_key = "SCENA_INSTAGRAM_ACCESS_TOKEN"

    def publish(self, snapshot):
        problem = self._validate(snapshot)
        if problem:
            return problem
        try:
            payload = self._request("POST", f"{self.account_id}/media", data={"image_url": snapshot["image_url"], "caption": snapshot["caption"]})
        except (MetaTransportError, TimeoutError, OSError) as exc:
            return self._request_failure(exc, mutating=True)
        container_id = str(payload.get("id", ""))
        if not _graph_id(container_id):
            return self._result("unknown", error_code="missing_container", message="Площадка не вернула идентификатор подготовки. Проверьте аккаунт.")
        return self.check_status(self._result("processing", container_id=container_id))

    def check_status(self, result):
        """Explicit continuation, no loop/sleep and never container recreation.

        A known pending upload can progress to publication. Unknown outcomes are
        only inspected, never POSTed again. Caller must hold its durable dispatch
        lock and persist this entire receipt, including publish_attempted.
        """
        if not self.configured:
            return self._fail("not_configured", "Подключение не настроено.")
        if not isinstance(result, Mapping) or result.get("account_id") != self.account_id or result.get("channel") != self.channel or result.get("configuration_fingerprint") != self.configuration_status()["fingerprint"]:
            return self._fail("configuration_changed", "Подключение изменилось. Обратитесь к оператору для проверки отправки.")
        if result.get("status") == "sent":
            return dict(result)
        container_id = result.get("container_id", "")
        if result.get("status") not in {"processing", "unknown"} or not _graph_id(container_id):
            return self._fail("invalid_receipt", "Нет подтверждённой подготовки для проверки. Автоматический повтор запрещён.")
        attempted = result.get("publish_attempted") is True
        can_publish = result.get("status") == "processing" and result.get("publish_attempted") is False
        try:
            payload = self._request("GET", container_id, fields="status_code")
        except (MetaTransportError, TimeoutError, OSError):
            return self._result("unknown" if attempted or result["status"] == "unknown" else "processing", container_id=container_id, publish_attempted=attempted, error_code="status_unavailable", message="Статус временно недоступен. Подготовка сохранена; повторите проверку позже.")
        state = payload.get("status_code")
        if state == "PUBLISHED":
            # A Graph container confirms publication, but cannot supply a media
            # permalink by itself. Do not fabricate an external media identifier.
            return self._result("sent", container_id=container_id, publish_attempted=True, message="Instagram подтвердил публикацию. Ссылка пока не получена; откройте свой аккаунт.")
        if state in {"ERROR", "EXPIRED"}:
            return self._result("unknown" if attempted else "failed", container_id=container_id, publish_attempted=attempted, error_code="container_" + state.lower(), message="Подготовка завершилась ошибкой или истекла. Проверьте аккаунт перед новой отправкой.")
        if state == "FINISHED" and can_publish:
            return self._publish_container(container_id)
        if state in {"IN_PROGRESS", "FINISHED"}:
            return self._result("unknown" if not can_publish else "processing", container_id=container_id, publish_attempted=attempted, message="Проверьте результат в Instagram. Повторной публикации не будет." if not can_publish else "Instagram обрабатывает фотографию. Проверьте статус примерно через минуту.")
        return self._result("unknown", container_id=container_id, publish_attempted=attempted, error_code="unrecognized_status", message="Площадка вернула неизвестный статус. Отправка приостановлена.")

    def _publish_container(self, container_id):
        try:
            payload = self._request("POST", f"{self.account_id}/media_publish", data={"creation_id": container_id})
        except (MetaTransportError, TimeoutError, OSError) as exc:
            return self._request_failure(exc, mutating=True, container_id=container_id, publish_attempted=True)
        media_id = str(payload.get("id", ""))
        if not _graph_id(media_id):
            return self._result("unknown", container_id=container_id, publish_attempted=True, error_code="missing_receipt", message="Площадка ответила без идентификатора публикации. Проверьте Instagram.")
        permalink = ""
        try:
            payload = self._request("GET", media_id, fields="permalink")
            candidate = payload.get("permalink", "")
            if is_public_https_url(candidate) and urlsplit(candidate).hostname in {"instagram.com", "www.instagram.com"}:
                permalink = candidate
        except (MetaTransportError, TimeoutError, OSError):
            # Successful media_publish is the receipt. Link lookup failure must
            # never turn it into a retryable publication failure.
            pass
        return self._result("sent", container_id=container_id, external_id=media_id, url=permalink, publish_attempted=True)


def get_adapters(env=None, transport=None):
    """Construct configured/offline adapters without querying Meta."""
    return {"facebook": FacebookPagesAdapter(env=env, transport=transport), "instagram": InstagramAdapter(env=env, transport=transport)}
