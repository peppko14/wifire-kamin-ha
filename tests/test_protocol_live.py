# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Tests für den zentralen WiFire-Live-Decoder."""

from __future__ import annotations

import unittest

from protocol import LiveStatus, decode_live_status


CLOSED_RAW = "aacc33550f0020001800010100000000ffff01ff3803"
OPEN_RAW = "aacc33550f0010001764000000000000ffff01ff8903"


class LiveStatusDecoderTests(unittest.TestCase):
    def test_closed_live_status_uses_central_model(self) -> None:
        status = decode_live_status(CLOSED_RAW)

        self.assertIsInstance(status, LiveStatus)
        self.assertEqual(status.temperature_c, 24)
        self.assertEqual(status.flap_percent, 0)
        self.assertFalse(status.flap_moving)
        self.assertEqual(status.burn_time, "1:01")
        self.assertEqual(status.burn_total_minutes, 61)
        self.assertFalse(status.door_open)
        self.assertEqual(status.door_state, "geschlossen")
        self.assertEqual(status.fan_raw, 1)
        self.assertEqual(status.raw, CLOSED_RAW)

    def test_open_door_and_full_flap_are_decoded(self) -> None:
        status = decode_live_status(OPEN_RAW)

        self.assertEqual(status.temperature_c, 23)
        self.assertEqual(status.flap_percent, 100)
        self.assertTrue(status.door_open)
        self.assertEqual(status.door_state, "offen")

    def test_moving_flap_is_clamped_like_previous_decoder(self) -> None:
        data = bytearray.fromhex(CLOSED_RAW)
        data[9] = 180

        status = decode_live_status(data.hex())

        self.assertEqual(status.flap_percent, 30)
        self.assertTrue(status.flap_moving)

    def test_mqtt_payload_contract_is_unchanged(self) -> None:
        payload = decode_live_status(CLOSED_RAW).to_mqtt_dict()

        self.assertEqual(
            tuple(payload),
            (
                "temperature_c",
                "flap_percent",
                "flap_moving",
                "burn_time",
                "burn_total_minutes",
                "door_open",
                "door_state",
                "fan_raw",
            ),
        )

    def test_invalid_hex_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Hex"):
            decode_live_status("not-hex")

    def test_short_packet_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "zu kurz"):
            decode_live_status("aacc3355")

    def test_unknown_header_is_rejected(self) -> None:
        data = bytearray.fromhex(CLOSED_RAW)
        data[0] = 0

        with self.assertRaisesRegex(ValueError, "Paketkopf"):
            decode_live_status(data.hex())


if __name__ == "__main__":
    unittest.main()
