import http.server
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import yaml

import account
import config
import gamecheckin
import hoyo_checkin
import login
import main
import main_multi
import os_cloudgames
import push
import request
from error import ConfigError, CookieError


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        state = patch.multiple(config, config=config.copy_config(), serverless=False, update_config_need=False)
        state.start()
        self.addCleanup(state.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def test_failed_write_preserves_original_and_allows_next_account_to_save(self):
        first = self.directory / "first.yaml"
        second = self.directory / "second.yaml"
        original = b"version: 15\n"
        first.write_bytes(original)
        with patch.object(Path, "replace", side_effect=PermissionError("read-only")):
            self.assertFalse(config.save_config(first, {"version": 15, "enable": False}))
        self.assertEqual(first.read_bytes(), original)
        self.assertEqual(list(self.directory.iterdir()), [first])
        self.assertFalse(config.serverless)
        self.assertTrue(config.save_config(second, {}))
        self.assertEqual(yaml.safe_load(second.read_text(encoding="utf-8")), {})

    def test_quoted_legacy_version_migrates_with_empty_fields(self):
        path = self.directory / "old.yaml"
        path.write_text('version: "12"\ncloud_games: null\ndevice: null\n', encoding="utf-8")
        loaded = config.load_config(path)
        self.assertEqual(loaded["version"], 15)
        self.assertEqual(loaded["device"]["fp"], "")
        self.assertTrue(config.update_config_need)
        self.assertEqual(yaml.safe_load(path.read_text(encoding="utf-8"))["version"], 15)
        config.load_config(path)
        self.assertFalse(config.update_config_need)

    def test_future_version_is_preserved(self):
        path = self.directory / "future.yaml"
        original = b"version: 99\nfuture_setting: 123\n"
        path.write_bytes(original)
        loaded = config.load_config(path)
        self.assertEqual(loaded["version"], 99)
        self.assertEqual(loaded["future_setting"], 123)
        self.assertEqual(path.read_bytes(), original)

    def test_unreadable_yaml_resets_last_account(self):
        valid = self.directory / "valid.yaml"
        invalid = self.directory / "invalid.yaml"
        valid.write_text("version: 15\naccount:\n  cookie: example=first\n", encoding="utf-8")
        invalid.write_bytes(b"\xff")
        config.load_config(valid)
        with self.assertRaises(ConfigError):
            config.load_config(invalid)
        self.assertEqual(config.config["account"]["cookie"], "")

    def test_multi_skips_directories_and_restores_the_single_user_configuration(self):
        (self.directory / "a.yml").write_text("version: 15\nenable: false\n", encoding="utf-8")
        (self.directory / "z.yaml").write_text(
            "version: 14\nmihoyobbs: {enable: false}\ngames: {cn: {enable: false}}\n",
            encoding="utf-8",
        )
        (self.directory / "b.yaml").mkdir()
        single_path = self.directory / "single.ini"
        original_config = config.config
        with (
            patch.multiple(config, path=str(self.directory), config_Path=single_path, config_prefix=""),
            patch.dict(os.environ, {"GITHUB_ACTIONS": "false", "AutoMihoyoBBS_config_multi": "0"}),
            patch.object(main_multi.time, "sleep") as sleep,
        ):
            self.assertEqual(main_multi.get_config_list(), ["a.yml", "z.yaml"])
            status, summary = main_multi.main_multi(True)
            self.assertEqual(status, 2)
            self.assertIn("a.yml", summary)
            self.assertIs(config.config, original_config)
            self.assertEqual(config.config_Path, single_path)
            self.assertTrue(config.update_config_need)
            sleep.assert_called_once()


class SessionTests(unittest.TestCase):
    def test_http_and_https_send_requests_to_the_configured_proxy(self):
        class Proxy(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(self.path.encode())

            def do_CONNECT(self):
                tunnel_targets.append(self.path)
                self.send_error(403)

            def log_message(self, *_args):
                pass

        tunnel_targets = []
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Proxy) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                proxy = f"127.0.0.1:{server.server_port}"
                with request.get_new_session_use_proxy(proxy) as client:
                    self.assertIsInstance(client, httpx.Client)
                    target = "http://checkin.invalid/test"
                    self.assertEqual(client.get(target).text, target)
                    with self.assertRaises(httpx.ProxyError):
                        client.get("https://checkin.invalid/test")
                self.assertEqual(tunnel_targets, ["checkin.invalid:443"])
            finally:
                server.shutdown()
                thread.join()

    def test_main_clears_shared_cookies_before_and_after_a_run(self):
        cookies_at_start = []

        def fail(_report):
            cookies_at_start.extend(main.http.cookies)
            main.http.cookies.set("test", "current")
            raise RuntimeError("mock failure")

        main.http.cookies.set("test", "previous")
        with patch.object(main, "_main", side_effect=fail):
            self.assertEqual(main.main()[0], 1)
        self.assertEqual(cookies_at_start, [])
        self.assertFalse(main.http.cookies)


class AccountTests(unittest.TestCase):
    def test_expired_account_list_retries_only_once(self):
        with (
            patch.object(account, "get_new_session") as session,
            patch.object(login, "update_cookie_token", return_value=True) as refresh,
        ):
            client = session.return_value.__enter__.return_value
            client.get.return_value.json.return_value = {"retcode": -100}
            with self.assertRaises(CookieError):
                account.get_account_list("hk4e_cn", {})
            self.assertEqual(client.get.call_count, 2)
            self.assertEqual(session.return_value.__exit__.call_count, 2)
            refresh.assert_called_once()

    def test_refresh_replaces_only_the_cookie_token_value(self):
        for old_token in ("same", ""):
            with self.subTest(old_token=old_token):
                current = config.copy_config()
                current["account"]["cookie"] = f"ltoken=same; cookie_token={old_token}; name=same"
                with (
                    patch.object(config, "config", current),
                    patch.object(config, "save_config") as save,
                    patch.object(login, "get_cookie_token_by_stoken", return_value="fresh"),
                ):
                    self.assertTrue(login.update_cookie_token())
                    self.assertEqual(current["account"]["cookie"], "ltoken=same; cookie_token=fresh; name=same")
                    save.assert_called_once()


class CheckinTests(unittest.TestCase):
    def test_cn_only_labels_an_explicit_challenge_as_captcha(self):
        game = object.__new__(gamecheckin.GameCheckin)
        game.game_name = game.game_mid = "genshin"
        game.player_name = "玩家"
        game.account_list = [("测试", "123", "cn")]
        game.is_sign = Mock(return_value={"is_sign": False, "total_sign_day": 0})
        for data, captcha in (
            ({"retcode": -100, "data": None}, False),
            ({"retcode": 0, "data": {"success": 1}}, True),
        ):
            with self.subTest(data=data), patch.object(gamecheckin.time, "sleep"):
                game.check_in = Mock(return_value=httpx.Response(200, json=data))
                errors = []
                result = game.sign_account(errors)
                self.assertEqual("触发验证码" in result, captcha)
                self.assertEqual(bool(errors), not captcha)

    def test_overseas_api_failure_reaches_summary(self):
        current = config.copy_config()
        current["games"]["os"].update({"enable": True, "cookie": "test=1", "genshin": {"checkin": True}})
        with patch.object(config, "config", current), patch.object(hoyo_checkin, "get_new_session") as session:
            session.return_value.get.return_value.json.return_value = {"retcode": -100}
            errors = []
            hoyo_checkin.run_task(errors)
            self.assertIn("retcode=-100", errors[0])

    def test_overseas_second_sign_in_reports_the_second_reward(self):
        with (
            patch.object(hoyo_checkin, "get_new_session") as session,
            patch.object(hoyo_checkin.time, "sleep"),
        ):
            client = session.return_value
            client.get.side_effect = [
                httpx.Response(200, json={"retcode": 0, "data": {"total_sign_day": 1}}),
                httpx.Response(200, json={"data": {"awards": [
                    {"cnt": 1, "name": "day one"}, {"cnt": 2, "name": "day two"},
                ]}}),
            ]
            client.post.return_value = httpx.Response(200, json={"retcode": 0})
            message = hoyo_checkin.hoyo_checkin("https://checkin.invalid", "test")
            self.assertIn("2x 「day two」", message)

    def test_overseas_cloud_header_values_are_strings(self):
        game = os_cloudgames.CloudGenshin("example", "zh-cn")
        self.assertEqual(httpx.Headers(game.headers)["x-rpc-client_type"], "3")


class PushTests(unittest.TestCase):
    def test_explicit_failure_and_unknown_service_are_not_reported_as_success(self):
        handler = push.PushHandler()
        handler.cfg.read_string("[setting]\nenable = true\npush_server = qbot, smtp, load_config")
        with (
            patch.object(handler, "load_config", return_value=True) as load,
            patch.object(handler, "smtp", return_value=None) as smtp,
            patch.object(handler, "qbot", return_value=1) as qbot,
            patch.object(config, "update_config_need", False),
        ):
            self.assertEqual(handler.push(1, "test"), 1)
            smtp.assert_called_once_with(1, "test")
            qbot.assert_called_once_with(1, "test")
            load.assert_called_once()

    def test_telegram_rejection_returns_failure_and_closes_proxy_session(self):
        handler = push.PushHandler()
        handler.cfg.read_string(
            "[telegram]\napi_url = example.invalid\nbot_token = fake\nchat_id = 1\nhttp_proxy = localhost:8080"
        )
        with patch.object(push, "get_new_session_use_proxy") as factory:
            session = factory.return_value
            session.__enter__.return_value.post.return_value = httpx.Response(403)
            self.assertEqual(handler.telegram(1, "test"), 1)
            factory.assert_called_once_with("localhost:8080")
            session.__exit__.assert_called_once()
