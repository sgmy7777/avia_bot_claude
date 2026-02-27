from __future__ import annotations
import logging
import re
import time

from bs4 import BeautifulSoup
import httpx

logger = logging.getLogger(__name__)


class AviationSafetyCollector:
    def __init__(self, user_agent: str, feed_urls: list[str]) -> None:
        self._headers = {"User-Agent": user_agent}
        self._feed_urls = feed_urls

    def fetch_recent_incidents(self) -> list[dict[str, str]]:
        errors: list[str] = []
        had_success_response = False
        with httpx.Client(headers=self._headers, timeout=20.0, follow_redirects=True) as client:
            for url in self._feed_urls:
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    had_success_response = True
                    incidents = self._parse_source(response.text)
                    if incidents:
                        logger.info("collector fetched %d rows from %s", len(incidents), url)
                        return incidents
                    errors.append(f"{url}: parsed 0 incidents")
                except Exception as exc:
                    errors.append(f"{url}: {exc}")
        if had_success_response:
            logger.warning("ASN source returned no parseable incidents. %s", " | ".join(errors))
            return []
        raise RuntimeError("ASN source unavailable. " + " | ".join(errors))

    def fetch_incident_details(self, source_url: str) -> dict[str, str]:
        if not source_url:
            return {}
        try:
            with httpx.Client(headers=self._headers, timeout=20.0, follow_redirects=True) as client:
                response = client.get(source_url)
                response.raise_for_status()
            return self._parse_incident_detail(response.text)
        except Exception as exc:
            logger.warning("failed to fetch incident details from %s: %s", source_url, exc)
            return {}

    def _parse_source(self, body: str) -> list[dict[str, str]]:
        payload = body.lstrip()
        if payload.startswith("<?xml") or "<rss" in payload[:300].lower():
            return self._parse_rss(payload)
        return self._parse_incident_table(payload)

    def _parse_rss(self, xml_text: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(xml_text, "xml")
        incidents: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for item in soup.find_all("item"):
            link_node = item.find("link")
            title_node = item.find("title")
            date_node = item.find("pubDate")
            link = (link_node.get_text(strip=True) if link_node else "").strip()
            title = " ".join((title_node.get_text(" ", strip=True) if title_node else "").split())
            pub_date = " ".join((date_node.get_text(" ", strip=True) if date_node else "").split())
            if not link or not title or link in seen_urls:
                continue
            seen_urls.add(link)
            incidents.append({"title": title, "event_type": "incident", "date_utc": pub_date,
                               "location": "", "aircraft": "", "operator": "", "persons_onboard": "",
                               "summary": title, "source_url": link})
        return incidents

    def _parse_incident_table(self, html: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(html, "lxml")
        incidents = self._parse_table_rows(soup)
        if incidents:
            return incidents
        return self._parse_incident_links(soup)

    def _parse_table_rows(self, soup) -> list[dict[str, str]]:
        incidents = []
        rows = soup.select("table.hp tr") or soup.select("table.list tr") or soup.select("table tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            anchor = row.find("a", href=True)
            if not anchor:
                continue
            href = anchor.get("href", "")
            source_url = href if href.startswith("http") else f"https://aviation-safety.net/{href.lstrip('/')}"
            title = " ".join(cols[3].get_text(" ", strip=True).split())
            date_text = cols[0].get_text(" ", strip=True)
            location = cols[1].get_text(" ", strip=True)
            aircraft = cols[2].get_text(" ", strip=True)
            if not any([title, date_text, location, aircraft]):
                continue
            incidents.append({"title": title, "event_type": "incident", "date_utc": date_text,
                               "location": location, "aircraft": aircraft, "operator": "",
                               "persons_onboard": "", "summary": title, "source_url": source_url})
        return incidents

    def _parse_incident_links(self, soup) -> list[dict[str, str]]:
        incidents = []
        seen_urls: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")
            if not self._is_incident_link(href):
                continue
            source_url = href if href.startswith("http") else f"https://aviation-safety.net/{href.lstrip('/')}"
            if source_url in seen_urls:
                continue
            seen_urls.add(source_url)
            title = " ".join(anchor.get_text(" ", strip=True).split())
            if not title:
                continue
            incidents.append({"title": title, "event_type": "incident", "date_utc": "",
                               "location": "", "aircraft": "", "operator": "", "persons_onboard": "",
                               "summary": title, "source_url": source_url})
        return incidents

    def _parse_incident_detail(self, html: str) -> dict[str, str]:  # noqa: PLR0912
        soup = BeautifulSoup(html, "lxml")

        title_node = soup.find("h1") or soup.find("title")
        title = " ".join(title_node.get_text(" ", strip=True).split()) if title_node else ""

        # Собираем все поля из таблицы фактов
        fields: dict[str, str] = {}
        for row in soup.select("table tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            key = cells[0].get_text(" ", strip=True).lower().strip(": ")
            val = " ".join(cells[1].get_text(" ", strip=True).split())
            if val:
                fields[key] = val

        # Маппинг полей ASN -> наши поля
        operator  = fields.get("owner/operator") or fields.get("operator") or ""
        aircraft  = fields.get("type") or fields.get("aircraft type") or fields.get("aircraft") or ""
        location  = fields.get("location") or ""
        date_utc  = fields.get("date") or ""
        time_utc  = fields.get("time") or ""
        registration   = fields.get("registration") or ""
        fatalities_raw = fields.get("fatalities") or ""
        departure      = fields.get("departure airport") or ""
        destination    = fields.get("destination airport") or ""
        phase          = fields.get("phase") or ""
        nature         = fields.get("nature") or ""
        persons_onboard = ""

        # Извлекаем число на борту из строки вида "Fatalities: 0 / Occupants: 1"
        if fatalities_raw:
            occ_match = re.search(r"[Oo]ccupants?[:\s]+(\d+)", fatalities_raw)
            if occ_match:
                persons_onboard = occ_match.group(1)
            fat_match = re.search(r"[Ff]atalit\w+[:\s]+(\d+)", fatalities_raw)
            fatalities = fat_match.group(1) if fat_match else ""
        else:
            fatalities = ""

        # Narrative — ищем отдельный блок или параграфы достаточной длины
        narrative = ""
        # Сначала ищем явный заголовок "Narrative" на странице
        for tag in soup.find_all(["h2", "h3", "b", "strong", "td", "th"]):
            if "narrative" in tag.get_text(strip=True).lower():
                # Берём следующий контент после заголовка
                sibling = tag.find_next(["p", "td", "div"])
                if sibling:
                    candidate = " ".join(sibling.get_text(" ", strip=True).split())
                    if len(candidate) >= 30:
                        narrative = candidate
                        break

        # Если не нашли явный narrative — собираем параграфы
        if not narrative:
            parts = []
            for node in soup.select("p"):
                text = " ".join(node.get_text(" ", strip=True).split())
                if len(text) >= 40:
                    parts.append(text)
            narrative = "\n".join(parts[:5]).strip()

        # Собираем расширенный summary для промпта
        summary_parts: list[str] = []
        if narrative:
            summary_parts.append(f"Нарратив: {narrative}")
        if phase:
            summary_parts.append(f"Фаза полёта: {phase}")
        if nature:
            summary_parts.append(f"Характер полёта: {nature}")
        if departure:
            summary_parts.append(f"Аэропорт вылета: {departure}")
        if destination and destination != departure:
            summary_parts.append(f"Аэропорт назначения: {destination}")
        if fatalities:
            summary_parts.append(f"Погибших: {fatalities}")

        summary = "\n".join(summary_parts).strip()

        # Обогащаем aircraft регистрацией если есть
        if registration and aircraft and registration not in aircraft:
            aircraft = f"{aircraft} (борт {registration})"

        # Добавляем время к дате если есть
        if time_utc and date_utc and time_utc not in date_utc:
            date_utc = f"{date_utc}, {time_utc}"

        result: dict[str, str] = {}
        if title:           result["title"]           = title
        if summary:         result["summary"]         = summary
        if operator:        result["operator"]        = operator
        if aircraft:        result["aircraft"]        = aircraft
        if location:        result["location"]        = location
        if date_utc:        result["date_utc"]        = date_utc
        if persons_onboard: result["persons_onboard"] = persons_onboard
        return result

    @staticmethod
    def _is_incident_link(href: str) -> bool:
        lowered = href.lower()
        return ("/wikibase/" in lowered or "/database/record.php" in lowered
                or "/database/db" in lowered or "/asndb/" in lowered)
