#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""
Werkzeug zur Untersuchung des Archivabschluss-Zeitpunkts während eines echten Abbrands.

Zeichnet periodisch Live-Daten und den Zustand von Archivplatz 1 auf, um festzustellen,
zu welchem genauen Zeitpunkt (Klappe 0 %, Phasenübergang, Schließzeitverzögerung etc.)
der Kamin den Abbrand ins Archiv überführt und als vollständig markiert.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Callable
from urllib.request import Request, urlopen


__version__ = "1.0.0"

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

try:
    from config import REQUEST_TIMEOUT as CONFIG_TIMEOUT, WIFIRE_URL as CONFIG_URL  # noqa: E402
except ImportError:
    CONFIG_TIMEOUT = 15
    CONFIG_URL = "http://192.168.0.1/direct/00"

from history.identifiers import build_burn_id  # noqa: E402
from protocol.adapters import archive_record_to_burn_record  # noqa: E402
from protocol.archive import ArchiveClient, ArchiveReadError  # noqa: E402
from protocol.live import decode_live_status  # noqa: E402
from protocol.models import LiveStatus  # noqa: E402
from wifire_protocol import decode_archive_record  # noqa: E402


MIN_INTER_REQUEST_DELAY = 10.0
DEFAULT_CYCLE_INTERVAL = 300.0  # 5 Minuten
DEFAULT_ARCHIVE_SLOT = 1
CONFIRMATION_THRESHOLD = 2


@dataclass(frozen=True, slots=True)
class ProbeSample:
    """Einzelne Momentaufnahme von Live- und Archivzustand."""

    timestamp_iso: str
    live_temperature_c: int | None
    live_flap_percent: int | None
    live_flap_moving: bool | None
    live_status_raw: int | None
    live_door_open: bool | None
    live_burn_time: str | None
    live_burn_total_minutes: int | None
    live_read_error: str | None
    archive_slot: int
    archive_fingerprint: str | None
    archive_timestamp_iso: str | None
    archive_measurement_count: int | None
    archive_active_or_incomplete: bool | None
    archive_is_complete: bool | None
    archive_burn_id: str | None
    archive_read_error: str | None
    event_message: str | None


@dataclass(slots=True)
class ProbeTracker:
    """Verfolgt Zustandsänderungen und Bestätigungen über mehrere Zyklen."""

    previous_fingerprint: str | None = None
    previous_burn_id: str | None = None
    consecutive_complete_matches: int = 0
    confirmed_complete: bool = False
    new_slot_detected: bool = False
    flap_zero_logged: bool = False

    def observe(
        self,
        *,
        live_flap: int | None,
        archive_fingerprint: str | None,
        archive_is_complete: bool | None,
        archive_active_or_incomplete: bool | None,
        burn_id: str | None,
    ) -> str | None:
        """Ermittelt Zustandswechsel und gibt Ereignismeldungen zurück."""
        events: list[str] = []

        if live_flap == 0 and not self.flap_zero_logged:
            self.flap_zero_logged = True
            events.append("Klappe 0 % erreicht")

        if archive_fingerprint is not None:
            if self.previous_fingerprint is not None and archive_fingerprint != self.previous_fingerprint:
                self.new_slot_detected = True
                self.consecutive_complete_matches = 0
                self.confirmed_complete = False
                events.append("neuer Archivplatz 1 erkannt")
            self.previous_fingerprint = archive_fingerprint

        if archive_active_or_incomplete is True:
            events.append("Datensatz noch unvollständig (active_or_incomplete=True)")
            self.consecutive_complete_matches = 0
        elif archive_is_complete is True and burn_id is not None:
            if burn_id == self.previous_burn_id:
                self.consecutive_complete_matches += 1
            else:
                self.consecutive_complete_matches = 1
                self.previous_burn_id = burn_id

            if not self.confirmed_complete:
                events.append(
                    f"Datensatz vollständig (Burn-ID: {burn_id[:12]}..., "
                    f"Treffer {self.consecutive_complete_matches}/{CONFIRMATION_THRESHOLD})"
                )

            if (
                self.consecutive_complete_matches >= CONFIRMATION_THRESHOLD
                and not self.confirmed_complete
            ):
                self.confirmed_complete = True
                events.append(
                    f"BESTÄTIGT: Archivdatensatz stabil und abgeschlossen! (Burn-ID: {burn_id})"
                )

        return " | ".join(events) if events else None


def fetch_live_raw(live_url: str, timeout: int) -> str:
    """Liest den rohen Live-Datensatz lesend über HTTP GET."""
    request = Request(
        live_url,
        headers={
            "Accept": "application/json",
            "Connection": "close",
        },
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    raw = payload.get("raw")
    if not isinstance(raw, str):
        raise ValueError("Die Antwort enthält kein gültiges Feld 'raw'.")
    return raw


def perform_probe_cycle(
    *,
    live_url: str,
    archive_client: ArchiveClient,
    slot: int,
    inter_request_delay: float,
    timeout: int,
    tracker: ProbeTracker,
    sleep_fn: Callable[[float], None] = time.sleep,
    logger: Callable[[str], None] = print,
) -> ProbeSample:
    """Führt genau einen synchronen Probe-Zyklus durch."""
    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")

    # 1. Live-Daten abfragen
    live_status: LiveStatus | None = None
    live_error: str | None = None
    try:
        live_raw = fetch_live_raw(live_url, timeout)
        live_status = decode_live_status(live_raw)
    except Exception as error:
        live_error = str(error)

    # Schutzpause für WiFire-Hardware (mindestens 10 Sekunden)
    sleep_fn(inter_request_delay)

    # 2. Archivplatz abfragen
    archive_fingerprint: str | None = None
    archive_timestamp_iso: str | None = None
    archive_measurement_count: int | None = None
    archive_active_or_incomplete: bool | None = None
    archive_is_complete: bool | None = None
    archive_burn_id: str | None = None
    archive_error: str | None = None

    try:
        archive_raw = archive_client.read_raw(slot)
        archive_fingerprint = hashlib.sha256(archive_raw.encode("utf-8")).hexdigest()[:16]
        archive_record = decode_archive_record(archive_raw)
        archive_measurement_count = len(archive_record.temperatures)
        archive_active_or_incomplete = archive_record.active_or_incomplete

        if archive_record.timestamp is not None:
            archive_timestamp_iso = archive_record.timestamp.isoformat(timespec="seconds")

        burn_record = archive_record_to_burn_record(archive_record)
        archive_is_complete = burn_record.is_complete

        if archive_is_complete and burn_record.start is not None and burn_record.temperatures_c:
            archive_burn_id = build_burn_id(burn_record)

    except (ArchiveReadError, ValueError, OSError) as error:
        archive_error = str(error)

    # 3. Zustandswechsel analysieren
    event = tracker.observe(
        live_flap=live_status.flap_percent if live_status else None,
        archive_fingerprint=archive_fingerprint,
        archive_is_complete=archive_is_complete,
        archive_active_or_incomplete=archive_active_or_incomplete,
        burn_id=archive_burn_id,
    )

    sample = ProbeSample(
        timestamp_iso=now_iso,
        live_temperature_c=live_status.temperature_c if live_status else None,
        live_flap_percent=live_status.flap_percent if live_status else None,
        live_flap_moving=live_status.flap_moving if live_status else None,
        live_status_raw=live_status.status_raw if live_status else None,
        live_door_open=live_status.door_open if live_status else None,
        live_burn_time=live_status.burn_time if live_status else None,
        live_burn_total_minutes=live_status.burn_total_minutes if live_status else None,
        live_read_error=live_error,
        archive_slot=slot,
        archive_fingerprint=archive_fingerprint,
        archive_timestamp_iso=archive_timestamp_iso,
        archive_measurement_count=archive_measurement_count,
        archive_active_or_incomplete=archive_active_or_incomplete,
        archive_is_complete=archive_is_complete,
        archive_burn_id=archive_burn_id,
        archive_read_error=archive_error,
        event_message=event,
    )

    # 4. Protokollzeile ausgeben
    live_summary = (
        f"{sample.live_temperature_c} °C, Klappe {sample.live_flap_percent} %, "
        f"Dauer {sample.live_burn_time}, Status 0x{sample.live_status_raw:02x}"
        if live_status
        else f"FEHLER: {live_error}"
    )
    archive_summary = (
        f"FP {sample.archive_fingerprint}, {sample.archive_measurement_count} Pkt, "
        f"active_incomplete={sample.archive_active_or_incomplete}, "
        f"ID {sample.archive_burn_id[:8] + '...' if sample.archive_burn_id else '-'}"
        if archive_fingerprint
        else f"FEHLER: {archive_error}"
    )

    log_line = f"[{sample.timestamp_iso}] Live: [{live_summary}] | Archiv {slot}: [{archive_summary}]"
    if event:
        log_line += f"  ===> {event}"
    logger(log_line)

    return sample


def run_probe(
    *,
    live_url: str,
    interval: float,
    inter_request_delay: float,
    timeout: int,
    slot: int,
    output_dir: Path,
    max_samples: int | None = None,
    stop_check: Callable[[], bool] = lambda: False,
    sleep_fn: Callable[[float], None] = time.sleep,
    logger: Callable[[str], None] = print,
) -> Path:
    """Führt die Aufzeichnung bis zum Abbruch oder Erreichen von max_samples durch."""
    output_dir.mkdir(parents=True, exist_ok=True)
    start_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = output_dir / f"probe_{start_tag}.jsonl"

    archive_client = ArchiveClient(
        live_url=live_url,
        request_timeout=timeout,
        retry_count=1,
        retry_delay_seconds=inter_request_delay,
    )

    tracker = ProbeTracker()
    samples_count = 0

    logger("=" * 70)
    logger(f"WiFire Archive Completion Probe v{__version__}")
    logger(f"Startzeit:             {datetime.now().astimezone().isoformat(timespec='seconds')}")
    logger(f"Live-URL:              {live_url}")
    logger(f"Beobachteter Slot:     {slot}")
    logger(f"Zyklus-Intervall:      {interval}s")
    logger(f"Abstand Live->Archiv:  {inter_request_delay}s")
    logger(f"Logdatei:              {log_path}")
    logger("=" * 70)

    try:
        with log_path.open("a", encoding="utf-8") as file:
            while not stop_check():
                cycle_start = time.monotonic()

                sample = perform_probe_cycle(
                    live_url=live_url,
                    archive_client=archive_client,
                    slot=slot,
                    inter_request_delay=inter_request_delay,
                    timeout=timeout,
                    tracker=tracker,
                    sleep_fn=sleep_fn,
                    logger=logger,
                )

                file.write(json.dumps(asdict(sample), ensure_ascii=False) + "\n")
                file.flush()

                samples_count += 1
                if max_samples is not None and samples_count >= max_samples:
                    logger(f"Maximale Probenanzahl ({max_samples}) erreicht.")
                    break

                elapsed = time.monotonic() - cycle_start
                remaining = max(1.0, interval - elapsed)

                # Wartezeit in 1-Sekunden-Schritten, damit SIGINT zeitnah greift
                steps = int(remaining)
                for _ in range(steps):
                    if stop_check():
                        break
                    sleep_fn(1.0)

    except KeyboardInterrupt:
        logger("\nAufzeichnung durch Benutzer beendet.")

    logger("=" * 70)
    logger(f"Probe beendet. Insgesamt {samples_count} Proben gespeichert.")
    logger(f"Ergebnis-Log: {log_path}")
    if tracker.confirmed_complete:
        logger(f"Status: Vollständiger Archivabschluss bestätigt! ID: {tracker.previous_burn_id}")
    else:
        logger("Status: Kein stabiler Archivabschluss innerhalb der Laufzeit bestätigt.")
    logger("=" * 70)

    return log_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Untersucht den exakten Zeitpunkt des WiFire-Archivabschlusses."
    )
    parser.add_argument(
        "--url",
        type=str,
        default=CONFIG_URL,
        help=f"WiFire Live-URL (Standard: {CONFIG_URL})",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_CYCLE_INTERVAL,
        help=f"Abfragezyklus in Sekunden (Standard: {DEFAULT_CYCLE_INTERVAL}s = 5 Min)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=MIN_INTER_REQUEST_DELAY,
        help=f"Verzögerung zwischen Live- und Archivrequest in Sekunden (mind. {MIN_INTER_REQUEST_DELAY}s)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=CONFIG_TIMEOUT,
        help=f"HTTP-Timeout in Sekunden (Standard: {CONFIG_TIMEOUT}s)",
    )
    parser.add_argument(
        "--slot",
        type=int,
        default=DEFAULT_ARCHIVE_SLOT,
        help=f"Zu beobachtender Archivplatz (Standard: {DEFAULT_ARCHIVE_SLOT})",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Maximale Anzahl Messpunkte (Standard: unbegrenzt)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(PROJECT_DIR / "data" / "archive-completion-probe"),
        help="Zielordner für Aufzeichnungsdaten",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.delay < MIN_INTER_REQUEST_DELAY:
        sys.exit(f"--delay muss mindestens {MIN_INTER_REQUEST_DELAY} Sekunden betragen.")
    if args.interval < args.delay + 5:
        sys.exit(f"--interval muss größer als delay ({args.delay}s) sein.")

    run_probe(
        live_url=args.url,
        interval=args.interval,
        inter_request_delay=args.delay,
        timeout=args.timeout,
        slot=args.slot,
        output_dir=Path(args.output_dir),
        max_samples=args.max_samples,
    )


if __name__ == "__main__":
    main()
