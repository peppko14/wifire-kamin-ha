#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 peppko14
# SPDX-License-Identifier: GPL-3.0-only

"""Strukturelle Tests für den gehärteten systemd-Dienst."""

from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SYSTEMD_DIR = PROJECT_ROOT / "systemd"
TEMPLATE_PATH = SYSTEMD_DIR / "wifire-kamin.service.template"
INSTALLER_PATH = SYSTEMD_DIR / "install_service_v0.12.4.sh"
UNINSTALLER_PATH = SYSTEMD_DIR / "uninstall_service_v0.12.4.sh"


class SystemdHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = TEMPLATE_PATH.read_text(encoding="utf-8")
        cls.installer = INSTALLER_PATH.read_text(encoding="utf-8")

    def test_template_contains_required_sandbox_settings(self) -> None:
        required_lines = {
            "NoNewPrivileges=true",
            "CapabilityBoundingSet=",
            "AmbientCapabilities=",
            "ProtectSystem=strict",
            "ProtectHome=read-only",
            "ReadWritePaths=@PROJECT_DIR@/data",
            "PrivateTmp=true",
            "PrivateDevices=true",
            "PrivateIPC=true",
            "ProtectControlGroups=true",
            "ProtectKernelTunables=true",
            "ProtectKernelModules=true",
            "ProtectKernelLogs=true",
            "ProtectClock=true",
            "ProtectHostname=true",
            "ProtectProc=invisible",
            "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
            "RestrictNamespaces=true",
            "RestrictRealtime=true",
            "RestrictSUIDSGID=true",
            "LockPersonality=true",
            "MemoryDenyWriteExecute=true",
            "SystemCallArchitectures=native",
            "UMask=0077",
        }

        template_lines = set(self.template.splitlines())
        self.assertEqual(required_lines - template_lines, set())

    def test_template_keeps_required_network_access(self) -> None:
        self.assertNotIn("PrivateNetwork=true", self.template.splitlines())
        self.assertNotIn("IPAddressDeny=any", self.template.splitlines())

    def test_template_keeps_project_visible_read_only(self) -> None:
        self.assertIn("ProtectHome=read-only", self.template.splitlines())
        self.assertNotIn("ProtectHome=true", self.template.splitlines())
        self.assertIn(
            "Environment=PYTHONDONTWRITEBYTECODE=1",
            self.template.splitlines(),
        )

    def test_installer_prepares_private_writable_paths(self) -> None:
        self.assertIn('chmod 0600 "${CONFIG_FILE}"', self.installer)
        self.assertIn("install -d", self.installer)
        self.assertIn('"${DATA_DIR}"', self.installer)
        self.assertIn("-m 0700", self.installer)

    def test_installer_verifies_before_installing_unit(self) -> None:
        verify_index = self.installer.index(
            'systemd-analyze verify "${TEMP_TARGET}"'
        )
        install_index = self.installer.index(
            'install -m 0644 "${TEMP_TARGET}" "${TARGET}"'
        )

        self.assertLess(verify_index, install_index)

    def test_current_install_and_uninstall_scripts_exist(self) -> None:
        self.assertTrue(INSTALLER_PATH.is_file())
        self.assertTrue(UNINSTALLER_PATH.is_file())
        self.assertFalse(
            (SYSTEMD_DIR / "install_service_v0.5.1.sh").exists()
        )
        self.assertFalse(
            (SYSTEMD_DIR / "uninstall_service_v0.5.1.sh").exists()
        )


if __name__ == "__main__":
    unittest.main()
