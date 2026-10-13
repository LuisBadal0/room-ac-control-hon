"""Locale selection, display-only translation and isolated preference storage."""
import ast
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from string import Formatter
import tempfile
import unittest
from unittest.mock import Mock, patch

from room_ac_control.i18n import Translator, system_language, resolve_language
from room_ac_control.translations import PORTUGUESE
from room_ac_control.secure_state import SecureState
from room_ac_control.functions_view import matches_search
from room_ac_control.controller import FIELDS


class LanguageTests(unittest.TestCase):
    def test_windows_display_language_is_used_and_unsupported_languages_fall_back(self):
        kernel = Mock()
        kernel.GetUserDefaultUILanguage.return_value = 0x0816
        with patch("room_ac_control.i18n.ctypes.WinDLL", return_value=kernel):
            self.assertEqual(resolve_language(system_language()), "pt-PT")
            self.assertEqual(Translator().language, "pt-PT")
        with patch("room_ac_control.i18n.system_language", return_value="fr-FR"):
            self.assertEqual(Translator().language, "en")
        self.assertEqual(resolve_language("pt_BR"), "pt-PT")

    def test_explicit_override_and_return_to_system(self):
        with patch("room_ac_control.i18n.system_language", return_value="pt_PT"):
            language = Translator("en")
            self.assertEqual(language.translate("Settings"), "Settings")
            language.set_language("system")
            self.assertEqual(language.translate("Settings"), "Definições")
            language.set_language("en")
            self.assertEqual(language.translate("Settings"), "Settings")

    def test_templates_preserve_dynamic_error_types_and_unknown_labels(self):
        language = Translator("pt-PT")
        message = "The cloud service returned an unexpected response (KeyError). The community integration may need updating."
        self.assertIn("(KeyError)", language.translate(message))
        self.assertNotEqual(language.translate(message), message)
        self.assertEqual(language.translate("New vendor function"), "New vendor function")
        self.assertEqual(language.translate("3 results across all functions"), "3 resultados em todas as funções")
        self.assertEqual(language.translate("Range 16–30 · Step 0.5"), "Intervalo 16–30 · Passo 0,5")

    def test_date_and_decimal_display_do_not_change_process_locale(self):
        before = __import__("locale").getlocale()
        language = Translator("pt-PT")
        self.assertEqual(language.number("23.5"), "23,5")
        self.assertEqual(language.date(datetime(2026,10,13)), "ter. 13 out.")
        self.assertEqual(Translator("en").date(datetime(2026,10,13)), "Tue 13 Oct")
        self.assertEqual(__import__("locale").getlocale(), before)

    def test_catalogue_preserves_template_fields_and_covers_known_controls_and_errors(self):
        fields = lambda text:{field for _,field,_,_ in Formatter().parse(text) if field}
        for source,target in PORTUGUESE.items():
            self.assertEqual(fields(source), fields(target), source)
        for label in FIELDS.values():self.assertIn(label, PORTUGUESE)
        folder = Path(__file__).resolve().parents[1]/"src"/"room_ac_control"
        for filename in ("controller.py", "cloud_timers.py"):
            for node in ast.walk(ast.parse((folder/filename).read_text(encoding="utf8"))):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=="ControlError":
                    if isinstance(node.args[0],ast.Constant):self.assertIn(node.args[0].value, PORTUGUESE)

    def test_search_finds_portuguese_labels_without_accents_and_english_aliases(self):
        item = {"kind":"setting", "label":"Vertical airflow", "spec":{"label":"Vertical airflow","options":{"Position 1":"2"}}}
        self.assertTrue(matches_search(item, "posicao 1"))
        self.assertTrue(matches_search(item, "fluxo vertical"))
        self.assertTrue(matches_search(item, "position 1"))
        self.assertFalse(matches_search(item, "posição 5"))

    def test_preference_survives_restart_and_sign_out_without_changing_account_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"state.dpapi"
            state=SecureState(path)
            self.assertEqual(state.language(), "system")
            state.save_credentials("fixture@example.test", "fake-language-test-password")
            state.save_profile("fixture", "fixture-ac", "cool", {"tempSel":"23.5","machMode":"1"})
            profiles=deepcopy(state.data["profiles"])
            state.save_language("pt-PT")
            reopened=SecureState(path)
            self.assertEqual(reopened.language(), "pt-PT")
            self.assertEqual(reopened.credentials(), state.credentials())
            self.assertEqual(reopened.data["profiles"], profiles)
            reopened.forget_credentials()
            self.assertEqual(SecureState(path).language(), "pt-PT")
            reopened.save_language("system")
            self.assertEqual(SecureState(path).language(), "system")

    def test_failed_preference_write_rolls_back_and_invalid_preferences_are_safe(self):
        state=SecureState(persistent=False)
        before=deepcopy(state.data)
        with patch.object(state,"write",side_effect=OSError("fixture")):
            with self.assertRaises(OSError):state.save_language("pt-PT")
        self.assertEqual(state.data,before)
        for value in ("fr", {}, None):
            state.data["language"]=value
            self.assertEqual(state.language(), "system")
            with self.assertRaises(ValueError):state.save_language(value)
