from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from backend.app.services import tdx_download_service as service


class TdxDownloadServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.raw_dir = self.root / "raw"
        self.download_dir = self.root / "downloads"
        self.zip_path = self.download_dir / "hsjday.zip"
        self.manifest_path = self.download_dir / "manifest.json"
        self.download_dir.mkdir(parents=True)
        self.patchers = [
            patch.object(service.settings, "raw_dir", self.raw_dir),
            patch.object(service, "DOWNLOAD_DIR", self.download_dir),
            patch.object(service, "ZIP_PATH", self.zip_path),
            patch.object(service, "MANIFEST_PATH", self.manifest_path),
            patch.object(service, "_status", service.TdxDownloadStatus()),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def _make_zip(self) -> None:
        with zipfile.ZipFile(self.zip_path, "w") as archive:
            archive.writestr("vipdoc/sh/lday/sh600000.day", b"sh-data")
            archive.writestr("vipdoc/sz/lday/sz000001.day", b"sz-data")
            archive.writestr("../../outside.txt", b"must-not-extract")
            archive.writestr("vipdoc/bj/lday/bj920001.day", b"bj-data")

    def test_extracts_only_sh_sz_day_files_inside_raw_dir(self) -> None:
        self._make_zip()

        service._extract_zip(self.zip_path)

        self.assertEqual((self.raw_dir / "sh/lday/sh600000.day").read_bytes(), b"sh-data")
        self.assertEqual((self.raw_dir / "sz/lday/sz000001.day").read_bytes(), b"sz-data")
        self.assertFalse((self.root / "outside.txt").exists())
        self.assertFalse((self.raw_dir / "bj/lday/bj920001.day").exists())
        self.assertEqual(service._status.extracted, 2)

    def test_remote_info_bypasses_cdn_cache_and_reads_zip_validators(self) -> None:
        info_response = Mock(
            text=(
                'window.HSJDAY_SOFT_SIZE="522.56MB"; '
                'window.HSJDAY_SOFT_TIME="2026-09-02 15:58:51";'
            )
        )
        zip_response = Mock()
        zip_response.headers = {
            "ETag": '"new-etag"',
            "Last-Modified": "Wed, 02 Sep 2026 07:58:51 GMT",
            "Content-Length": "547952185",
        }
        client = Mock()
        client.get.return_value = info_response
        client.head.return_value = zip_response

        with patch.object(service.httpx, "Client") as client_factory:
            client_factory.return_value.__enter__.return_value = client
            result = service.fetch_remote_info()

        client_factory.assert_called_once()
        headers = client_factory.call_args.kwargs["headers"]
        self.assertEqual(headers["Cache-Control"], "no-cache")
        self.assertEqual(headers["Pragma"], "no-cache")
        get_params = client.get.call_args.kwargs["params"]
        head_params = client.head.call_args.kwargs["params"]
        self.assertTrue(get_params["_"])
        self.assertEqual(head_params, get_params)
        self.assertEqual(result["update_time"], "2026-09-02 15:58:51")
        self.assertEqual(result["zip_etag"], '"new-etag"')
        self.assertEqual(
            result["zip_last_modified"], "Wed, 02 Sep 2026 07:58:51 GMT"
        )

    def test_unchanged_remote_version_reuses_local_zip(self) -> None:
        self._make_zip()
        service._write_manifest({"remote_time": "2026-08-26 15:58:48"})
        remote = {
            "url": service.TDX_ZIP_URL,
            "size": "521.70MB",
            "update_time": "2026-08-26 15:58:48",
        }

        with (
            patch.object(service, "fetch_remote_info", return_value=remote),
            patch.object(service, "_download_zip") as download,
            patch.object(service, "_extract_zip") as extract,
            patch.object(service, "_sync_gbbq", return_value={}) as sync_gbbq,
            patch.object(service, "_run_incremental_build") as build,
        ):
            service._run_sync(force_download=False)

        download.assert_not_called()
        extract.assert_not_called()
        sync_gbbq.assert_called_once_with(force_download=False)
        build.assert_called_once_with()
        self.assertEqual(service._status.stage, "done")
        self.assertFalse(service._status.downloaded)

    def test_changed_zip_validator_downloads_even_if_version_js_is_stale(self) -> None:
        self._make_zip()
        service._write_manifest(
            {
                "remote_time": "2026-09-01 15:58:58",
                "zip_etag": '"old-etag"',
            }
        )
        remote = {
            "url": service.TDX_ZIP_URL,
            "size": "522.39MB",
            "update_time": "2026-09-01 15:58:58",
            "zip_etag": '"new-etag"',
        }

        with (
            patch.object(service, "fetch_remote_info", return_value=remote),
            patch.object(service, "_download_zip") as download,
            patch.object(service, "_extract_zip") as extract,
            patch.object(service, "_sync_gbbq", return_value={}),
            patch.object(service, "_run_incremental_build"),
        ):
            service._run_sync(force_download=False)

        download.assert_called_once_with()
        extract.assert_called_once_with(self.zip_path)
        self.assertTrue(service._status.downloaded)

    def test_status_read_does_not_request_network(self) -> None:
        with patch.object(service, "fetch_remote_info", side_effect=AssertionError("network called")):
            payload = service.status_payload()

        self.assertEqual(payload["source_url"], service.TDX_ZIP_URL)
        self.assertFalse(payload["running"])


if __name__ == "__main__":
    unittest.main()
