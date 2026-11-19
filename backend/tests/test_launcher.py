"""Unit tests for Desktop Application Launcher modules."""

import os
import tempfile
import unittest
from pathlib import Path

from launcher.config import get_app_root, get_asset_path, load_env_dict, update_env_variable
from launcher.ip_guard import IPGuardStatus, get_local_hostname, get_local_lan_ip
from launcher.supervisor import find_python_interpreter, get_preferred_bind_port, is_port_in_use


class TestLauncherConfig(unittest.TestCase):
    """Test configuration discovery, asset resolution, and atomic .env updating."""

    def test_app_root_exists(self):
        root = get_app_root()
        self.assertTrue(root.exists())
        self.assertTrue((root / "backend").exists())

    def test_asset_path_resolution(self):
        assets_dir = get_asset_path()
        self.assertTrue(assets_dir.exists())
        ico_file = get_asset_path("app_icon.ico")
        self.assertTrue(ico_file.exists())
        png_file = get_asset_path("app_icon.png")
        self.assertTrue(png_file.exists())
        symbol_file = get_asset_path("algo_symbol.png")
        self.assertTrue(symbol_file.exists())

    def test_update_env_variable(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".env") as tf:
            tf.write("EXISTING_KEY=old_value\n# Comment\nFOO=bar\n")
            temp_path = Path(tf.name)

        try:
            from launcher import config
            orig_get_env_paths = config.get_env_paths
            config.get_env_paths = lambda: [temp_path]

            update_env_variable("EXISTING_KEY", "new_value")
            content = temp_path.read_text()
            self.assertIn('EXISTING_KEY="new_value"', content)
            self.assertIn("# Comment", content)
            self.assertIn("FOO=bar", content)

            # Test appending new variable
            update_env_variable("NEW_KEY", "hello_world")
            content_after = temp_path.read_text()
            self.assertIn('NEW_KEY="hello_world"', content_after)

            config.get_env_paths = orig_get_env_paths
        finally:
            if temp_path.exists():
                temp_path.unlink()


class TestIPGuard(unittest.TestCase):
    """Test IP detection, LAN IP resolution, and status evaluation."""

    def test_local_lan_ip(self):
        lan_ip = get_local_lan_ip()
        self.assertIsInstance(lan_ip, str)
        self.assertTrue(len(lan_ip.split(".")) == 4)

    def test_local_hostname(self):
        host = get_local_hostname()
        self.assertIsInstance(host, str)
        self.assertTrue(host.endswith(".local"))

    def test_ip_guard_status_structure(self):
        guard = IPGuardStatus()
        self.assertIn(guard.status_label, ["CHECKING...", "OFFLINE", "WHITELISTED", "IP MISMATCH", "NOT CONFIGURED"])
        self.assertIsInstance(guard.lan_ip, str)
        self.assertIsInstance(guard.registered_ips, list)


class TestSupervisorUtilities(unittest.TestCase):
    """Test port checks, python interpreter discovery, and bind port preference."""

    def test_find_python_interpreter(self):
        py_exe = find_python_interpreter()
        self.assertTrue(os.path.exists(py_exe))
        import subprocess
        res = subprocess.run([py_exe, "-c", "import uvicorn, celery"], capture_output=True)
        self.assertEqual(res.returncode, 0, f"Interpreter {py_exe} missing uvicorn/celery: {res.stderr.decode()}")

    def test_is_port_in_use_structure(self):
        # Port 0 or a very unlikely port should be false
        self.assertIsInstance(is_port_in_use("127.0.0.1", 64999), bool)

    def test_get_preferred_bind_port(self):
        port = get_preferred_bind_port()
        self.assertIn(port, [80, 8000])


if __name__ == "__main__":
    unittest.main()
