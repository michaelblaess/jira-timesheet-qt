"""Ladeanzeige der Statusleiste: vier Darstellungen, waehlbar unter Darstellung."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage, QRegion
from PySide6.QtWidgets import QApplication, QWidget

from jira_timesheet_qt.models.settings import (
    BUSY_CLASSIC,
    BUSY_COMET,
    BUSY_INDICATORS,
    BUSY_SEGMENTS,
    BUSY_SHIMMER,
    DEFAULT_BUSY_INDICATOR,
    Settings,
)
from jira_timesheet_qt.ui.busy_indicator import (
    BUSY_LABELS,
    SEGMENT_COUNT,
    BusyIndicator,
    pingpong,
    segment_glow,
)
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.settings_dialog import SettingsDialog
from jira_timesheet_qt.ui.theme import Mode, palette_for


def _frame(indicator: BusyIndicator, seconds: float) -> QImage:
    """Ein Bild zum Zeitpunkt `seconds`, auf dem dunklen Grund der Statusleiste."""
    indicator._clock = lambda: indicator._start + seconds
    image = QImage(indicator.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor(palette_for(Mode.DARK).bg_secondary))
    # Ohne DrawWindowBackground, sonst liegt der helle Fenstergrund darunter.
    indicator.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return image


def _head(image: QImage) -> int:
    """Die hellste Spalte der Mittelzeile - dort sitzt der Kopf des Kometen."""
    y = image.height() // 2
    return max(range(image.width()), key=lambda x: QColor(image.pixel(x, y)).lightness())


class TestEinstellung:
    def test_vorgabe_ist_das_lauflicht(self) -> None:
        assert Settings().busy_indicator == BUSY_SEGMENTS == DEFAULT_BUSY_INDICATOR

    def test_gespeicherter_wert_kommt_zurueck(self) -> None:
        Settings(busy_indicator=BUSY_COMET).save()
        assert Settings.load().busy_indicator == BUSY_COMET

    @pytest.mark.parametrize("raw", [None, "", "blinker", 3])
    def test_unbekannter_wert_faellt_auf_die_vorgabe(self, raw: object) -> None:
        assert Settings._from_dict({"busy_indicator": raw}).busy_indicator == DEFAULT_BUSY_INDICATOR

    def test_alte_datei_ohne_feld_bekommt_die_vorgabe(self) -> None:
        assert Settings._from_dict({}).busy_indicator == DEFAULT_BUSY_INDICATOR


class TestDialog:
    def test_alle_vier_stehen_zur_wahl_lauflicht_zuerst(self, qapp: QApplication) -> None:
        dialog = SettingsDialog(Settings())
        combo = dialog.busy_indicator
        keys = [combo.itemData(i) for i in range(combo.count())]
        assert keys == [BUSY_SEGMENTS, BUSY_COMET, BUSY_SHIMMER, BUSY_CLASSIC]
        assert set(keys) == set(BUSY_INDICATORS) == set(BUSY_LABELS)
        assert combo.currentData() == BUSY_SEGMENTS

    def test_auswahl_kommt_zurueck(self, qapp: QApplication) -> None:
        dialog = SettingsDialog(Settings(busy_indicator=BUSY_SHIMMER))
        assert dialog.busy_indicator.currentData() == BUSY_SHIMMER
        dialog.busy_indicator.setCurrentIndex(dialog.busy_indicator.findData(BUSY_CLASSIC))
        assert dialog.result_settings().busy_indicator == BUSY_CLASSIC


class TestAnzeige:
    def test_unbekannter_stil_faellt_auf_die_vorgabe(self, qapp: QApplication) -> None:
        assert BusyIndicator(Mode.DARK, "blinker").style_name == DEFAULT_BUSY_INDICATOR

    def test_klassisch_ist_der_alte_unbestimmte_balken(self, qapp: QApplication) -> None:
        indicator = BusyIndicator(Mode.DARK, BUSY_CLASSIC)
        indicator.show()
        assert indicator.classic_bar.isVisible() is True
        assert (indicator.classic_bar.minimum(), indicator.classic_bar.maximum()) == (0, 0)
        # Der alte Balken animiert sich selbst, der eigene Takt bleibt aus.
        assert indicator.animating is False

    @pytest.mark.parametrize("style", [BUSY_SEGMENTS, BUSY_COMET, BUSY_SHIMMER])
    def test_takt_laeuft_nur_solange_sichtbar(self, qapp: QApplication, style: str) -> None:
        indicator = BusyIndicator(Mode.DARK, style)
        assert indicator.animating is False
        indicator.show()
        assert indicator.animating is True
        assert indicator.classic_bar.isVisible() is False
        indicator.hide()
        assert indicator.animating is False

    def test_wechsel_auf_klassisch_stoppt_den_takt(self, qapp: QApplication) -> None:
        indicator = BusyIndicator(Mode.DARK, BUSY_COMET)
        indicator.show()
        indicator.set_style(BUSY_CLASSIC)
        assert indicator.animating is False

    @pytest.mark.parametrize("style", [BUSY_SEGMENTS, BUSY_COMET, BUSY_SHIMMER])
    def test_bewegt_sich(self, qapp: QApplication, style: str) -> None:
        indicator = BusyIndicator(Mode.DARK, style)
        assert _frame(indicator, 0.2) != _frame(indicator, 0.5)

    @pytest.mark.parametrize("style", [BUSY_SEGMENTS, BUSY_COMET, BUSY_SHIMMER])
    def test_zeichnet_in_der_akzentfarbe(self, qapp: QApplication, style: str) -> None:
        indicator = BusyIndicator(Mode.DARK, style)
        image = _frame(indicator, 0.3)
        accent = QColor(palette_for(Mode.DARK).accent)
        y = image.height() // 2
        hues = {QColor(image.pixel(x, y)).hue() for x in range(image.width())}
        assert any(abs(h - accent.hue()) <= 12 for h in hues if h >= 0)

    def test_komet_laeuft_hin_und_zurueck(self, qapp: QApplication) -> None:
        indicator = BusyIndicator(Mode.DARK, BUSY_COMET)
        links = _head(_frame(indicator, 0.05))
        mitte = _head(_frame(indicator, 0.4))
        rechts = _head(_frame(indicator, 0.8))
        zurueck = _head(_frame(indicator, 1.2))
        assert links < 15
        assert 50 < mitte < 70
        assert rechts > 105
        assert 50 < zurueck < 70


class TestBewegung:
    def test_pingpong_bremst_an_den_enden(self) -> None:
        assert pingpong(0.0, 2.0) == (0.0, 1)
        assert pingpong(0.5, 2.0)[0] == pytest.approx(0.5)
        assert pingpong(0.999, 2.0)[0] == pytest.approx(1.0, abs=1e-3)
        assert pingpong(1.5, 2.0) == (pytest.approx(0.5), -1)
        # Weich: am Rand bewegt er sich langsamer als in der Mitte.
        assert pingpong(0.05, 2.0)[0] < 0.05 / 1.0

    def test_lauflicht_kopf_leuchtet_dahinter_glueht_es_nach(self) -> None:
        # Bei 0,5 s steht der Kopf auf 5,5 - Segment 5 ist hell, 0 schon dunkel.
        glows = [segment_glow(0.5, i) for i in range(SEGMENT_COUNT)]
        assert glows[5] == max(glows)
        assert glows[4] < glows[5]
        assert glows[6] == 0.0
        assert glows[0] == 0.0


class TestHauptfenster:
    def test_fenster_nimmt_die_gespeicherte_darstellung(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(busy_indicator=BUSY_SHIMMER), Mode.DARK)
        assert window._busy.style_name == BUSY_SHIMMER

    def test_nach_dem_speichern_gilt_die_neue_darstellung(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from jira_timesheet_qt.ui import main_window as main_window_module

        window = MainWindow(Settings(), Mode.DARK)
        gespeichert = Settings(busy_indicator=BUSY_COMET)

        class _Dialog:
            DialogCode = SettingsDialog.DialogCode

            def __init__(self, *_args: object) -> None: ...

            def exec(self) -> int:
                return int(self.DialogCode.Accepted)

            def result_settings(self) -> Settings:
                return gespeichert

        monkeypatch.setattr(main_window_module, "SettingsDialog", _Dialog)
        window.open_settings()
        assert window._busy.style_name == BUSY_COMET

    def test_moduswechsel_faerbt_die_anzeige_neu(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window._mode = Mode.LIGHT
        window._reapply_theme()
        assert window._busy._palette == palette_for(Mode.LIGHT)
