import hashlib
import tempfile
import unittest
from pathlib import Path

from pastport_pdf_vr.adapters.assets import AssetStoreError, LocalAssetStore


class AssetRegistrationTests(unittest.TestCase):
    def test_multi_chunk_roundtrip_idempotency_corruption_and_bound(self) -> None:
        payload = b"a" * (1024 * 1024) + b"different second block" * 500
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.bin"
            source.write_bytes(payload)
            store = LocalAssetStore(root / "assets")
            first = store.register_file("test", source, "application/octet-stream", len(payload))
            self.assertEqual(first.reference.asset.sha256, hashlib.sha256(payload).hexdigest())
            registered = store.resolve_path(first.reference)
            self.assertEqual(registered.read_bytes(), payload)
            self.assertEqual(
                first,
                store.register_bytes("test", payload, "application/octet-stream", len(payload)),
            )
            with self.assertRaises(AssetStoreError):
                store.register_bytes("test", payload, "application/octet-stream", 10)
            registered.write_bytes(b"corrupted")
            with self.assertRaises(AssetStoreError):
                store.resolve_path(first.reference)
