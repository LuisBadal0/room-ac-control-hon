"""Offline checks for the MSI and Setup.exe recipe; nothing is installed."""
from pathlib import Path
import json
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_installers  # noqa: E402

WXS = "{http://wixtoolset.org/schemas/v4/wxs}"


class InstallerTests(unittest.TestCase):
    def test_release_names_sit_beside_the_portable_zip(self):
        names = build_installers.release_names("1.2.3")
        self.assertEqual(names, {"zip": "Room-AC-Control-for-hOn-1.2.3-Windows-x64.zip",
                                 "msi": "Room-AC-Control-for-hOn-1.2.3-Windows-x64.msi",
                                 "setup": "Room-AC-Control-for-hOn-1.2.3-Windows-x64-Setup.exe"})

    def test_stage_unpacks_only_the_app_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            archive, stage = Path(folder) / "release.zip", Path(folder) / "stage"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("Room AC Control/runtime/RoomACControl/RoomACControl.exe", b"exe")
                bundle.writestr("Room AC Control/README.md", b"readme")
                bundle.writestr("elsewhere.txt", b"ignored")
            build_installers.stage_files(archive, stage)
            files = sorted(path.relative_to(stage).as_posix() for path in stage.rglob("*") if path.is_file())
            self.assertEqual(files, ["README.md", "runtime/RoomACControl/RoomACControl.exe"])

    def test_stage_refuses_paths_that_leave_the_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "release.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("Room AC Control/runtime/RoomACControl/RoomACControl.exe", b"exe")
                bundle.writestr("Room AC Control/../outside.txt", b"bad")
            with self.assertRaises(RuntimeError):
                build_installers.stage_files(archive, Path(folder) / "stage")
            self.assertFalse((Path(folder) / "outside.txt").exists())

    def test_stage_requires_the_app_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "release.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("Room AC Control/README.md", b"readme")
            with self.assertRaises(RuntimeError):
                build_installers.stage_files(archive, Path(folder) / "stage")

    def test_license_page_is_plain_ascii_rtf(self):
        rtf = build_installers.license_rtf("MIT {x} \\ © 2026\nLine two\n")
        rtf.encode("ascii")
        self.assertTrue(rtf.startswith("{\\rtf1"))
        self.assertIn("\\{x\\} \\\\ \\u169? 2026\\par\nLine two", rtf)

    def test_package_installs_per_user_where_in_app_updates_can_write(self):
        package = ElementTree.parse(ROOT / "packaging" / "installer" / "RoomACControl.wxs").find(f"{WXS}Package")
        self.assertEqual(package.get("Scope"), "perUser")
        self.assertEqual(package.find(f"{WXS}StandardDirectory").get("Id"), "LocalAppDataFolder")
        # The updater only treats .../runtime/RoomACControl/RoomACControl.exe as an updatable install.
        targets = {shortcut.get("Target") for shortcut in package.iter(f"{WXS}Shortcut")}
        self.assertEqual(targets, {"[INSTALLFOLDER]runtime\\RoomACControl\\RoomACControl.exe"})
        self.assertIsNotNone(package.find(f"{WXS}MajorUpgrade"))

    def test_msi_desktop_shortcut_follows_its_checkbox(self):
        package = ElementTree.parse(ROOT / "packaging" / "installer" / "RoomACControl.wxs").find(f"{WXS}Package")
        components = {component.get("Id"): component for component in package.iter(f"{WXS}Component")}
        self.assertIsNone(components["StartMenuShortcut"].get("Condition"))
        self.assertEqual(components["DesktopShortcut"].get("Condition"),
                         'INSTALLDESKTOPSHORTCUT AND INSTALLDESKTOPSHORTCUT <> "0"')
        self.assertEqual(components["DesktopShortcut"].find(f"{WXS}Shortcut").get("Directory"), "DesktopFolder")
        secure = {prop.get("Id") for prop in package.iter(f"{WXS}Property") if prop.get("Secure") == "yes"}
        self.assertEqual(secure, {"INSTALLDESKTOPSHORTCUT", "DESKTOPCHOICEMADE"})
        self.assertEqual(package.find(f"{WXS}UIRef").get("Id"), "RoomACControlUI")

        ui = ElementTree.parse(ROOT / "packaging" / "installer" / "InstallerUI.wxs").find(f"{WXS}Fragment/{WXS}UI")
        self.assertEqual(ui.get("Id"), "RoomACControlUI")
        dialog = ui.find(f"{WXS}Dialog[@Id='ShortcutsDlg']")
        checkbox = dialog.find(f"{WXS}Control[@Type='CheckBox']")
        self.assertEqual((checkbox.get("Property"), checkbox.get("CheckBoxValue")), ("INSTALLDESKTOPSHORTCUT", "1"))
        steps = {(p.get("Dialog"), p.get("Control")): p.get("Value") for p in ui.iter(f"{WXS}Publish")
                 if p.get("Event") == "NewDialog" and p.get("Condition") in (None, "NOT Installed", 'LicenseAccepted = "1"')}
        self.assertEqual(steps[("LicenseAgreementDlg", "Next")], "ShortcutsDlg")
        self.assertEqual(steps[("ShortcutsDlg", "Next")], "VerifyReadyDlg")
        self.assertEqual(steps[("VerifyReadyDlg", "Back")], "ShortcutsDlg")

    def test_setup_exe_desktop_checkbox_reaches_the_msi(self):
        folder = ROOT / "packaging" / "installer"
        bundle = ElementTree.parse(folder / "Setup.wxs").find(f"{WXS}Bundle")
        variable = bundle.find(f"{WXS}Variable[@Name='InstallDesktopShortcut']")
        self.assertEqual(variable.get("{http://wixtoolset.org/schemas/v4/wxs/bal}Overridable"), "yes")
        properties = {p.get("Name"): p.get("Value") for p in bundle.iter(f"{WXS}MsiProperty")}
        self.assertEqual(properties, {"INSTALLDESKTOPSHORTCUT": "[InstallDesktopShortcut]", "DESKTOPCHOICEMADE": "1"})
        theme = ElementTree.parse(folder / "SetupTheme.xml").getroot()
        names = [box.get("Name") for box in theme.iter("{http://wixtoolset.org/schemas/v4/thmutil}Checkbox")]
        self.assertIn("InstallDesktopShortcut", names)
        strings = ElementTree.parse(folder / "SetupTheme.wxl").getroot()
        self.assertIn("InstallDesktopShortcutCheckbox",
                      {s.get("Id") for s in strings.iter("{http://wixtoolset.org/schemas/v4/wxl}String")})

    def test_msi_page_artwork_is_drawn_from_the_app_icon(self):
        dialog, banner = build_installers.dialog_artwork(), build_installers.banner_artwork()
        self.assertEqual((dialog.size, dialog.mode), ((493, 312), "RGB"))
        self.assertEqual((banner.size, banner.mode), ((493, 58), "RGB"))
        # Page text is drawn over these areas, so they stay plain white.
        self.assertEqual(dialog.crop((170, 0, 493, 312)).getextrema(), ((255, 255),) * 3)
        self.assertEqual(banner.crop((0, 0, 300, 58)).getextrema(), ((255, 255),) * 3)
        top_left = dialog.getpixel((5, 5))
        self.assertTrue(all(abs(a - b) <= 3 for a, b in zip(top_left, build_installers.BRAND)), top_left)
        package = (ROOT / "packaging" / "installer" / "RoomACControl.wxs").read_text(encoding="utf-8")
        self.assertIn('<WixVariable Id="WixUIDialogBmp" Value="$(var.DialogBmp)" />', package)
        self.assertIn('<WixVariable Id="WixUIBannerBmp" Value="$(var.BannerBmp)" />', package)

    def test_upgrade_codes_never_change(self):
        package = ElementTree.parse(ROOT / "packaging" / "installer" / "RoomACControl.wxs").find(f"{WXS}Package")
        bundle = ElementTree.parse(ROOT / "packaging" / "installer" / "Setup.wxs").find(f"{WXS}Bundle")
        self.assertEqual(package.get("UpgradeCode"), "14F7297C-2E07-4BB0-B0DF-D7054B996DDE")
        self.assertEqual(bundle.get("UpgradeCode"), "3CE84886-4F75-40A5-B136-E82F9D22EA78")

    def test_wix_tool_is_pinned_to_an_exact_version(self):
        tools = json.loads((ROOT / ".config" / "dotnet-tools.json").read_text(encoding="utf-8"))
        self.assertRegex(tools["tools"]["wix"]["version"], r"^\d+\.\d+\.\d+$")
        self.assertFalse(tools["tools"]["wix"]["rollForward"])

    def test_release_workflow_builds_and_publishes_both_installers(self):
        workflow = (ROOT / ".github" / "workflows" / "windows.yml").read_text(encoding="utf-8")
        self.assertIn("tools/build_installers.py", workflow)
        for pattern in ("releases/*.msi", "releases/*-Setup.exe"):
            self.assertIn(pattern, workflow)
        publish = re.search(r"gh release create .*?--generate-notes", workflow, re.DOTALL).group(0)
        self.assertIn("release/*.msi", publish)
        self.assertIn("release/*-Setup.exe", publish)


if __name__ == "__main__":
    unittest.main()
