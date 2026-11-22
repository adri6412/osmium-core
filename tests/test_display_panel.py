"""Settings → Display: the DSI panel selector (api_server.set_display_panel).

A DSI touch panel needs a device-tree overlay loaded at boot, so this selector is
a boot-config edit, not a runtime switch — the twin of the I2S DAC/HAT selector.
The backend persists the choice to a conf file on the shared /data /etc overlay
(so it survives OTA) and patches config.txt on the boot FATs. The FAT patching
needs real block devices, so it is stubbed here; what is pinned is the gating
(Pi-only, not during an update), the validation, the overlay availability filter,
and the saved conf.

The feature ships in the shared core and is gated on hifi_platform.is_raspberry()
(it reports `supported: False` and refuses writes on x86), so these tests drive
the platform marker through api_server's imported hifi_platform module.
"""
import json
import os
import tempfile
import unittest

import api_server as a


CATALOGUE = {
    "_source": "test",
    "panels": [
        {"id": "official-auto", "name": "Official Display", "detail": "auto",
         "overlay": "", "overlay_params": ""},
        {"id": "waveshare-7-0-c", "name": "Waveshare 7.0\" (C)", "detail": "1024x600",
         "overlay": "vc4-kms-dsi-waveshare-panel", "overlay_params": "7_0_inchC"},
        {"id": "ili9881-5", "name": "ILI9881 5\"", "detail": "720x1280",
         "overlay": "vc4-kms-dsi-ili9881-5inch", "overlay_params": ""},
    ],
}


class DisplayPanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.panels_file = os.path.join(root, 'display-panels.json')
        with open(self.panels_file, 'w', encoding='utf-8') as f:
            json.dump(CATALOGUE, f)
        self.panel_file = os.path.join(root, 'etc', 'display-panel.conf')

        self._saved = {}
        self._patch('DISPLAY_PANELS_FILE', self.panels_file)
        self._patch('DISPLAY_PANEL_FILE', self.panel_file)
        # No overlays dir to check against → the availability filter shows every
        # panel (it only hides overlays it can prove are absent).
        self._patch('DSI_OVERLAY_DIRS', ())
        a._display_panels_cache = None
        self._set_platform(True)
        self._patch('_update_in_progress', lambda: False)
        # Pretend both boot FATs were patched, so we test the backend's own logic
        # and not mount/umount of real partitions.
        self.applied = []
        self._patch('_apply_dsi_overlay_to_boot_fats',
                    lambda disp, touch: (self.applied.append((disp, touch))
                                         or (list(a.DAC_BOOT_PARTLABELS), [])))

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(a, name, value)
        a.hifi_platform.is_raspberry = self._platform_saved
        a._display_panels_cache = None
        self.tmp.cleanup()

    def _patch(self, name, value):
        self._saved[name] = getattr(a, name)
        setattr(a, name, value)

    def _set_platform(self, is_rpi):
        if not hasattr(self, '_platform_saved'):
            self._platform_saved = a.hifi_platform.is_raspberry
        a.hifi_platform.is_raspberry = lambda: is_rpi

    def _saved_conf(self):
        with open(self.panel_file, encoding='utf-8') as f:
            return dict(line.strip().split('=', 1) for line in f if '=' in line)

    # ── catalogue / gating ──────────────────────────────────────────
    def test_list_includes_catalogue(self):
        ids = [p['id'] for p in a.list_display_panels()['panels']]
        self.assertEqual(ids, ['official-auto', 'waveshare-7-0-c', 'ili9881-5'])

    def test_availability_filter_hides_absent_overlay(self):
        # A dir that exists but holds no .dtbo → overlay-backed panels are hidden,
        # the auto-detect panel (empty overlay) stays.
        a._display_panels_cache = None
        a.DSI_OVERLAY_DIRS = (self.tmp.name,)
        ids = [p['id'] for p in a.list_display_panels()['panels']]
        self.assertEqual(ids, ['official-auto'])

    def test_not_supported_off_pi(self):
        self._set_platform(False)
        out = a.list_display_panels()
        self.assertFalse(out['supported'])
        self.assertEqual(out['panels'], [])

    def test_set_refused_off_pi(self):
        self._set_platform(False)
        out = a.set_display_panel('waveshare-7-0-c')
        self.assertFalse(out['success'])
        self.assertFalse(os.path.exists(self.panel_file))

    def test_set_refused_during_update(self):
        a._update_in_progress = lambda: True
        out = a.set_display_panel('waveshare-7-0-c')
        self.assertFalse(out['success'])
        self.assertFalse(os.path.exists(self.panel_file))

    # ── apply a valid panel ─────────────────────────────────────────
    def test_set_valid_panel_persists_and_patches(self):
        out = a.set_display_panel('waveshare-7-0-c')
        self.assertTrue(out['success'])
        self.assertTrue(out['reboot_required'])
        self.assertEqual(out['current'], 'waveshare-7-0-c')
        conf = self._saved_conf()
        self.assertEqual(conf['id'], 'waveshare-7-0-c')
        self.assertEqual(conf['display'], 'vc4-kms-dsi-waveshare-panel,7_0_inchC')
        self.assertEqual(conf['touch'], '')
        self.assertEqual(self.applied, [('vc4-kms-dsi-waveshare-panel,7_0_inchC', '')])

    def test_set_panel_without_params(self):
        out = a.set_display_panel('ili9881-5')
        self.assertTrue(out['success'])
        self.assertEqual(self._saved_conf()['display'], 'vc4-kms-dsi-ili9881-5inch')

    def test_official_auto_has_empty_overlay(self):
        out = a.set_display_panel('official-auto')
        self.assertTrue(out['success'])
        self.assertEqual(self._saved_conf()['display'], '')
        self.assertEqual(self.applied[-1], ('', ''))

    def test_current_reflects_saved_choice(self):
        a.set_display_panel('waveshare-7-0-c')
        self.assertEqual(a.list_display_panels()['current'], 'waveshare-7-0-c')

    # ── clear / invalid ─────────────────────────────────────────────
    def test_none_clears_the_overlay(self):
        a.set_display_panel('waveshare-7-0-c')
        out = a.set_display_panel('none')
        self.assertTrue(out['success'])
        self.assertEqual(out['current'], '')
        self.assertEqual(self._saved_conf()['display'], '')
        self.assertEqual(self.applied[-1], ('', ''))

    def test_empty_clears_the_overlay(self):
        a.set_display_panel('waveshare-7-0-c')
        out = a.set_display_panel('')
        self.assertTrue(out['success'])
        self.assertEqual(self._saved_conf()['id'], '')

    def test_unknown_panel_rejected(self):
        out = a.set_display_panel('not-a-real-panel')
        self.assertFalse(out['success'])
        self.assertEqual(out['code'], 'dsi.invalidPanel')
        self.assertFalse(os.path.exists(self.panel_file))

    def test_patch_failure_surfaces(self):
        a._apply_dsi_overlay_to_boot_fats = lambda disp, touch: ([], ['hifi-boot-a (absent)'])
        out = a.set_display_panel('waveshare-7-0-c')
        self.assertFalse(out['success'])
        self.assertEqual(out['code'], 'dsi.applyFailed')


if __name__ == '__main__':
    unittest.main()
