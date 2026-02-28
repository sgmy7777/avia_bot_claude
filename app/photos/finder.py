from __future__ import annotations

"""
Поиск фото воздушных судов.

Стратегия (в порядке приоритета):
1. Planespotters.net API — фото конкретного борта по регистрации (N85RW)
2. Wikimedia Commons API — generic фото модели ВС (Piper PA-28)
3. None — если ничего не найдено, публикуем без фото
"""

import logging
import re
import urllib.parse

import httpx

logger = logging.getLogger(__name__)

# Planespotters отдаёт фото конкретного борта по регистрации
_PLANESPOTTERS_URL = "https://api.planespotters.net/pub/photos/reg/{reg}"

# Wikimedia Commons — поиск по ключевым словам
_WIKIMEDIA_SEARCH_URL = "https://commons.wikimedia.org/w/api.php"

# User-Agent обязателен для Wikimedia API
_USER_AGENT = "avia_bot/1.0 (https://github.com/sgmy7777/avia_bot)"


class PhotoFinder:
    def __init__(self, user_agent: str = _USER_AGENT) -> None:
        self._headers = {"User-Agent": user_agent}

    def find_photo(self, registration: str, aircraft_model: str) -> str | None:
        """
        Ищет фото ВС. Возвращает прямую ссылку на изображение или None.

        Args:
            registration: регистрационный номер борта (например "N85RW")
            aircraft_model: модель ВС (например "Piper PA-28-151 Cherokee Warrior")
        """
        # Чистим регистрацию от мусора вида "(борт N85RW)"
        reg = self._extract_registration(registration)

        # 1. Пробуем Planespotters по регистрации
        if reg:
            url = self._planespotters(reg)
            if url:
                logger.info("photo found on planespotters | reg=%s", reg)
                return url

        # 2. Пробуем Wikimedia по модели ВС
        if aircraft_model:
            url = self._wikimedia(aircraft_model)
            if url:
                logger.info("photo found on wikimedia | model=%s", aircraft_model)
                return url

        logger.info("no photo found | reg=%s model=%s", reg, aircraft_model)
        return None

    def _planespotters(self, registration: str) -> str | None:
        try:
            url = _PLANESPOTTERS_URL.format(reg=registration.upper())
            with httpx.Client(headers=self._headers, timeout=10.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()

            photos = data.get("photos", [])
            if not photos:
                return None

            # Берём первое фото, предпочитаем medium или large
            photo = photos[0]
            thumbnail = photo.get("thumbnail_large", {})
            src = thumbnail.get("src") or photo.get("thumbnail", {}).get("src")
            return src or None

        except Exception as exc:  # noqa: BLE001
            logger.debug("planespotters error for %s: %s", registration, exc)
            return None

    def _wikimedia(self, aircraft_model: str) -> str | None:
        try:
            # Упрощаем модель для лучшего поиска
            # "Piper PA-28-151 Cherokee Warrior (борт N85RW)" -> "Piper PA-28 Cherokee"
            query = self._simplify_model(aircraft_model)
            if not query:
                return None

            params = {
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrnamespace": "6",  # File namespace
                "gsrsearch": f"{query} aircraft",
                "gsrlimit": "5",
                "prop": "imageinfo",
                "iiprop": "url|mime",
                "iiurlwidth": "800",
            }

            with httpx.Client(headers=self._headers, timeout=10.0) as client:
                resp = client.get(_WIKIMEDIA_SEARCH_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

            pages = data.get("query", {}).get("pages", {})
            if not pages:
                return None

            for page in pages.values():
                imageinfo = page.get("imageinfo", [])
                if not imageinfo:
                    continue
                info = imageinfo[0]
                mime = info.get("mime", "")
                # Только JPEG и PNG, без SVG и иконок
                if mime not in ("image/jpeg", "image/png"):
                    continue
                url = info.get("thumburl") or info.get("url")
                if url:
                    return url

            return None

        except Exception as exc:  # noqa: BLE001
            logger.debug("wikimedia error for %s: %s", aircraft_model, exc)
            return None

    @staticmethod
    def _extract_registration(text: str) -> str:
        """Извлекает регистрацию из строки вида 'Piper PA-28 (борт N85RW)'."""
        if not text:
            return ""
        # Ищем паттерн борта
        m = re.search(r"\(борт\s+([A-Z0-9\-]+)\)", text)
        if m:
            return m.group(1)
        # Если строка сама по себе похожа на регистрацию
        text = text.strip()
        if re.match(r"^[A-Z0-9]{1,2}[-A-Z0-9]{2,6}$", text):
            return text
        return ""

    @staticmethod
    def _simplify_model(model: str) -> str:
        """
        Упрощает модель ВС для поиска на Wikimedia.
        'Piper PA-28-151 Cherokee Warrior (борт N85RW)' -> 'Piper PA-28 Cherokee'
        'Airbus A320-200' -> 'Airbus A320'
        'Boeing 737-800' -> 'Boeing 737'
        'Embraer ERJ-190LR' -> 'Embraer ERJ-190'
        """
        # Убираем "(борт ...)"
        model = re.sub(r"\(борт[^)]+\)", "", model).strip()

        # Убираем модификации в конце: -200, -800, LR, neo, XLR и т.д.
        model = re.sub(r"[-/]\d{3,}[A-Z]*\s*$", "", model).strip()

        # Убираем суб-варианты типа PA-28-151 -> PA-28
        model = re.sub(r"(\b[A-Z]{1,3}-\d{2,3})-\d{2,3}\b", r"\1", model)

        # Берём первые 4 слова
        words = model.split()
        return " ".join(words[:4]) if len(words) > 4 else model
