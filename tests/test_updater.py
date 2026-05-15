from __future__ import annotations

import unittest

from aelrith_forge.backend import updater


class FakeResponse:
    def __init__(self, payload=None, status_error: Exception | None = None):
        self.payload = payload
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


def release_payload(tag="v1.101", asset_name="Kon-v1.101-portable.zip", **extra):
    payload = {
        "tag_name": tag,
        "html_url": "https://github.example/releases/tag/v1.101",
        "draft": False,
        "prerelease": False,
        "body": "Release notes",
        "assets": [
            {
                "name": asset_name,
                "browser_download_url": "https://github.example/Kon-v1.101-portable.zip",
                "size": 12345,
            }
        ],
    }
    payload.update(extra)
    return payload


class UpdaterTests(unittest.TestCase):
    def test_version_comparison_handles_patch_padding(self):
        self.assertTrue(updater.is_newer_version("v1.101", "v1.100.25"))
        self.assertTrue(updater.is_newer_version("v1.101.1", "v1.101"))
        self.assertFalse(updater.is_newer_version("v1.101.0", "v1.101"))
        self.assertFalse(updater.is_newer_version("v1.99", "v1.100.25"))
        self.assertIsNone(updater.parse_version("v1.101-beta"))

    def test_check_for_update_reports_available_release_asset(self):
        session = FakeSession(FakeResponse(release_payload()))

        result = updater.check_for_update(current_version="v1.100.25", session=session)

        self.assertEqual(result.status, "available")
        self.assertTrue(result.update_available)
        self.assertEqual(result.latest_version, "v1.101")
        self.assertEqual(result.asset_name, "Kon-v1.101-portable.zip")
        self.assertEqual(result.asset_size, 12345)

    def test_check_for_update_reports_current_for_same_or_older_release(self):
        session = FakeSession(FakeResponse(release_payload(tag="v1.100.25", asset_name="Kon-v1.100.25-portable.zip")))

        result = updater.check_for_update(current_version="v1.100.25", session=session)

        self.assertEqual(result.status, "current")
        self.assertFalse(result.update_available)

    def test_check_for_update_ignores_draft_and_prerelease(self):
        draft = updater.check_for_update(
            current_version="v1.100.25",
            session=FakeSession(FakeResponse(release_payload(draft=True))),
        )
        prerelease = updater.check_for_update(
            current_version="v1.100.25",
            session=FakeSession(FakeResponse(release_payload(prerelease=True))),
        )

        self.assertEqual(draft.status, "current")
        self.assertEqual(prerelease.status, "current")

    def test_check_for_update_fails_for_missing_portable_asset(self):
        session = FakeSession(FakeResponse(release_payload(asset_name="Kon-source.zip")))

        result = updater.check_for_update(current_version="v1.100.25", session=session)

        self.assertEqual(result.status, "failed")
        self.assertIn("No portable release ZIP", result.message)

    def test_check_for_update_fails_for_network_or_malformed_release(self):
        network = updater.check_for_update(
            current_version="v1.100.25",
            session=FakeSession(error=RuntimeError("offline")),
        )
        malformed = updater.check_for_update(
            current_version="v1.100.25",
            session=FakeSession(FakeResponse(["not", "a", "release"])),
        )

        self.assertEqual(network.status, "failed")
        self.assertEqual(malformed.status, "failed")

    def test_preserved_update_dirs_include_local_runtime_state(self):
        preserved = set(updater.PRESERVED_UPDATE_DIRS)

        self.assertIn("config", preserved)
        self.assertIn("output", preserved)
        self.assertIn("logs", preserved)
        self.assertIn("screenshots", preserved)


if __name__ == "__main__":
    unittest.main()
