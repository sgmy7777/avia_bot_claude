from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class TelegramPublisher:
    def __init__(self, bot_token: str, channel: str, alert_chat_id: str = "") -> None:
        self._bot_token = bot_token
        self._channel = channel
        self._alert_chat_id = alert_chat_id  # служебный чат для алертов (fix #8)

    def publish(self, text: str) -> None:
        if not self._bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is empty")
        if not self._channel:
            raise RuntimeError("TELEGRAM_CHANNEL is empty")

        self._send(self._channel, text)

    def send_alert(self, message: str) -> None:
        """
        Отправляет алерт в служебный чат (fix #8).
        Если TELEGRAM_ALERT_CHAT_ID не задан — только логирует.
        """
        if not self._alert_chat_id:
            logger.warning("ALERT (no alert chat configured): %s", message)
            return
        if not self._bot_token:
            logger.warning("ALERT (no bot token): %s", message)
            return

        try:
            self._send(self._alert_chat_id, f"🚨 avia_bot ALERT\n\n{message}")
        except Exception as exc:  # noqa: BLE001
            logger.error("failed to send alert to %s: %s", self._alert_chat_id, exc)

    def _send(self, chat_id: str, text: str) -> None:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, json=payload)
            if response.is_success:
                return

            details = self._extract_telegram_error(response)

            # Fallback без parse_mode при ошибке парсинга entities
            if response.status_code == 400 and "can't parse entities" in details.lower():
                fallback_payload = {
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                }
                fallback_response = client.post(url, json=fallback_payload)
                if fallback_response.is_success:
                    return
                response = fallback_response
                details = self._extract_telegram_error(response)

        raise RuntimeError(
            "Telegram sendMessage failed. "
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
        if text:
            return text
        return "unknown error"
