from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class TelegramPublisher:
    def __init__(self, bot_token: str, channel: str, alert_chat_id: str = "") -> None:
        self._bot_token = bot_token
        self._channel = channel
        self._alert_chat_id = alert_chat_id

    def publish(self, text: str, photo_url: str | None = None) -> None:
        if not self._bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is empty")
        if not self._channel:
            raise RuntimeError("TELEGRAM_CHANNEL is empty")

        if photo_url:
            self._send_photo(self._channel, text, photo_url)
        else:
            self._send_text(self._channel, text)

    def send_alert(self, message: str) -> None:
        if not self._alert_chat_id:
            logger.warning("ALERT (no alert chat configured): %s", message)
            return
        if not self._bot_token:
            logger.warning("ALERT (no bot token): %s", message)
            return
        try:
            self._send_text(self._alert_chat_id, f"🚨 avia_bot ALERT\n\n{message}")
        except Exception as exc:  # noqa: BLE001
            logger.error("failed to send alert to %s: %s", self._alert_chat_id, exc)

    def _send_photo(self, chat_id: str, caption: str, photo_url: str) -> None:
        """
        Отправляет фото с подписью через sendPhoto.
        Если фото не загрузилось — fallback на обычный текстовый пост.
        """
        url = f"https://api.telegram.org/bot{self._bot_token}/sendPhoto"

        # Telegram caption ограничен 1024 символами
        if len(caption) > 1024:
            caption = caption[:1020] + "..."

        payload = {
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "Markdown",
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload)

            if response.is_success:
                return

            details = self._extract_telegram_error(response)
            logger.warning(
                "sendPhoto failed (status=%s, %s), falling back to text",
                response.status_code,
                details,
            )

            # Fallback — публикуем без фото
            self._send_text(chat_id, caption, client=client)

    def _send_text(
        self,
        chat_id: str,
        text: str,
        client: httpx.Client | None = None,
    ) -> None:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        def _post(c: httpx.Client) -> httpx.Response:
            return c.post(url, json=payload)

        def _post_no_parse(c: httpx.Client) -> httpx.Response:
            return c.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
            })

        if client is not None:
            response = _post(client)
            if response.is_success:
                return
            details = self._extract_telegram_error(response)
            if response.status_code == 400 and "can't parse entities" in details.lower():
                response = _post_no_parse(client)
                if response.is_success:
                    return
        else:
            with httpx.Client(timeout=20.0) as c:
                response = _post(c)
                if response.is_success:
                    return
                details = self._extract_telegram_error(response)
                if response.status_code == 400 and "can't parse entities" in details.lower():
                    response = _post_no_parse(c)
                    if response.is_success:
                        return
                    details = self._extract_telegram_error(response)

        details = self._extract_telegram_error(response)
        raise RuntimeError(
            f"Telegram sendMessage failed. "
            f"status={response.status_code}; chat_id={chat_id}; details={details}"
        )

    @staticmethod
    def _extract_telegram_error(response: httpx.Response) -> str:
        try:
            data = response.json()
            description = data.get("description")
            if description:
                return str(description)
        except Exception:  # noqa: BLE001
            pass
        text = response.text.strip()
        return text if text else "unknown error"
