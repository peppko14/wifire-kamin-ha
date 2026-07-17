# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Gemeinsamer, ausschließlich lesender Zugriff auf WiFire-Archive."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, ContextManager, Protocol
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from bridge.logging_setup import log_warning


MIN_ARCHIVE_NUMBER = 1
MAX_ARCHIVE_NUMBER = 255
ARCHIVE_ENDPOINT = "35"


class ArchiveReadError(RuntimeError):
    """Ein Archiv konnte nach allen Versuchen nicht gelesen werden."""


class HttpResponse(Protocol):
    """Für die Archivantwort benötigte minimale Schnittstelle."""

    def read(self) -> bytes:
        ...


class UrlOpener(Protocol):
    """Austauschbarer URL-Opener für Tests und Produktivbetrieb."""

    def __call__(
        self,
        request: Request,
        *,
        timeout: int,
    ) -> ContextManager[HttpResponse]:
        ...


Sleeper = Callable[[int | float], None]
Logger = Callable[[str], None]


def open_url(
    request: Request,
    *,
    timeout: int,
) -> ContextManager[HttpResponse]:
    """Öffnet den Request über die Standardbibliothek."""
    return urlopen(request, timeout=timeout)


def build_archive_url(live_url: str) -> str:
    """Leitet den Archivendpunkt `/direct/35` aus der Live-URL ab."""
    parsed = urlsplit(live_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("WIFIRE_URL ist keine gültige absolute URL.")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2 or path_parts[-2] != "direct":
        raise ValueError(
            "WIFIRE_URL muss auf einen Endpunkt unter /direct/ zeigen."
        )

    path_parts[-1] = ARCHIVE_ENDPOINT
    return urlunsplit(
        (parsed.scheme, parsed.netloc, "/" + "/".join(path_parts), "", "")
    )


def build_archive_command(number: int) -> str:
    """Erzeugt ausschließlich den bekannten lesenden Archivbefehl."""
    if (
        isinstance(number, bool)
        or not isinstance(number, int)
        or not MIN_ARCHIVE_NUMBER <= number <= MAX_ARCHIVE_NUMBER
    ):
        raise ValueError(
            "Archivnummer muss als Ganzzahl zwischen 1 und 255 liegen."
        )
    return f"aacc33550235{number:02x}ffff"


def build_archive_request(archive_url: str, number: int) -> Request:
    """Erzeugt einen fest definierten HTTP-Request für genau einen Platz."""
    body = json.dumps(
        {"raw": build_archive_command(number)}
    ).encode("utf-8")
    return Request(
        archive_url,
        data=body,
        headers={
            "Content-Type": "text/plain",
            "Accept": "application/json",
            "Connection": "close",
        },
        method="POST",
    )


@dataclass(frozen=True, slots=True)
class ArchiveClient:
    """Liest rohe Archivtelegramme mit begrenzten Wiederholungen."""

    live_url: str
    request_timeout: int = 15
    retry_count: int = 3
    retry_delay_seconds: int | float = 10
    sleeper: Sleeper = time.sleep
    opener: UrlOpener = open_url
    logger: Logger = print

    def __post_init__(self) -> None:
        build_archive_url(self.live_url)
        if (
            isinstance(self.request_timeout, bool)
            or not isinstance(self.request_timeout, int)
            or self.request_timeout < 1
        ):
            raise ValueError("request_timeout muss mindestens 1 sein.")
        if (
            isinstance(self.retry_count, bool)
            or not isinstance(self.retry_count, int)
            or self.retry_count < 1
        ):
            raise ValueError("retry_count muss mindestens 1 sein.")
        if (
            isinstance(self.retry_delay_seconds, bool)
            or not isinstance(self.retry_delay_seconds, (int, float))
            or self.retry_delay_seconds < 0
        ):
            raise ValueError(
                "retry_delay_seconds darf nicht negativ sein."
            )

    @property
    def archive_url(self) -> str:
        """Aus der Live-URL abgeleiteter Archivendpunkt."""
        return build_archive_url(self.live_url)

    def read_raw(self, number: int) -> str:
        """Liest genau einen Archivplatz und validiert das Hex-Telegramm."""
        # Aufruferfehler werden vor dem Retry-Block abgewiesen. Nur echte
        # Transport- und Antwortfehler dürfen einen erneuten Zugriff auslösen.
        build_archive_command(number)
        last_error: OSError | ValueError | None = None

        for attempt in range(1, self.retry_count + 1):
            try:
                request = build_archive_request(self.archive_url, number)
                with self.opener(
                    request,
                    timeout=self.request_timeout,
                ) as response:
                    result = json.loads(
                        response.read().decode("utf-8")
                    )

                if not isinstance(result, dict):
                    raise ValueError(
                        "Archivantwort ist kein JSON-Objekt."
                    )
                raw = result.get("raw")
                if not isinstance(raw, str) or not raw:
                    raise ValueError(
                        "Archivantwort enthält kein gültiges raw-Feld."
                    )
                bytes.fromhex(raw)
                return raw

            except (OSError, ValueError) as error:
                last_error = error
                log_warning(
                    self.logger,
                    f"Archiv {number}, Versuch {attempt}/"
                    f"{self.retry_count} fehlgeschlagen: {error}",
                )
                if attempt < self.retry_count:
                    self.sleeper(self.retry_delay_seconds)

        raise ArchiveReadError(
            f"Archiv {number} konnte nach {self.retry_count} Versuchen "
            f"nicht gelesen werden: {last_error}"
        )
