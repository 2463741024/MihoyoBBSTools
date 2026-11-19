import os
import time
import random
from typing import Tuple, Optional
from enum import Enum

import push
import login
import tools
import config
import mihoyobbs
import cloudgames
import gamecheckin
import hoyo_checkin
import web_activity
import os_cloudgames
from loghelper import log
from error import CookieError, StokenError, ConfigError
from request import http


class StatusCode(Enum):
    SUCCESS = 0
    FAILURE = 1
    PARTIAL_FAILURE = 2
    CAPTCHA_TRIGGERED = 3


PLANNED_SECTIONS = (
    "配置初始化", "登录", "米游社", "国服游戏签到", "国服云游戏签到",
    "国际服游戏签到", "国际服云游戏签到", "网页活动",
)


class RunReport:
    """记录各模块执行状态，用于失败时生成运行概况"""

    def __init__(self, sections=PLANNED_SECTIONS):
        self.order = list(sections)
        self.items = {name: {"status": "pending", "detail": ""} for name in self.order}

    def set(self, name: str, status: str, detail: str = "") -> None:
        if name not in self.items:
            self.order.append(name)
        self.items[name] = {"status": status, "detail": detail}

    def render(self) -> str:
        labels = (
            ("success", "已完成"),
            ("partial", "部分完成"),
            ("failed", "失败/未完成"),
            ("running", "执行中断"),
            ("skipped", "未启用"),
            ("pending", "未执行"),
        )
        lines = ["运行概况："]
        for status, label in labels:
            entries = []
            for name in self.order:
                item = self.items[name]
                if item["status"] != status:
                    continue
                detail = item["detail"]
                if detail and status in ("failed", "partial"):
                    entries.append(f"{name}（{detail}）")
                else:
                    entries.append(name)
            if entries:
                lines.append(f"- {label}：{'、'.join(entries)}")
        return "\n".join(lines)


last_report = None


def format_last_report() -> str:
    return last_report.render() if last_report else ""


def exception_message(error: Exception) -> str:
    """提取更友好的异常描述"""
    return str(getattr(error, "info", error))


def exception_detail(error: Exception) -> str:
    """提取异常类型、原因和最后出错位置"""
    detail = f"{type(error).__name__}: {exception_message(error)}"
    tb = error.__traceback__
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    if tb is not None:
        detail += f"（{os.path.basename(tb.tb_frame.f_code.co_filename)}:{tb.tb_lineno}）"
    return detail


def check_github_actions() -> None:
    """检查是否在GitHub Actions环境运行"""
    if os.getenv('GITHUB_ACTIONS') == 'true':
        log.error("请不要在 GitHub Action 运行本项目")
        exit(0)


def initialize_config() -> Tuple[bool, Optional[str]]:
    """初始化配置"""
    try:
        config.load_config()
    except ConfigError as e:
        log.error(str(e))
        return False, str(e)
    if not config.config["enable"]:
        log.warning("Config 未启用！")
        return False, "Config 未启用！"
    return True, None


def handle_login() -> None:
    """处理登录逻辑"""
    account_cfg = config.config["account"]
    if any([
        account_cfg["stuid"] == "",
        account_cfg["stoken"] == "",
        account_cfg["mid"] == ""
    ]):
        if config.config["mihoyobbs"]["enable"]:
            login.login()
            time.sleep(random.randint(3, 8))
        account_cfg["cookie"] = tools.tidy_cookie(account_cfg["cookie"])


def run_mihoyobbs(errors: list = None) -> str:
    """执行米游社签到任务"""
    if not config.config["mihoyobbs"]["enable"]:
        return ""
    if config.config["account"]["stoken"] == "StokenError":
        raise StokenError("账号 Stoken 异常")
    return mihoyobbs.Mihoyobbs().run_task(errors)


def run_web_activity(errors: list = None) -> str:
    """执行网页活动任务"""
    if not config.config["web_activity"]['enable']:
        return ""
    log.info("正在进行米游社网页活动任务")
    web_activity.run_task(errors)
    return ""


def main() -> Tuple[int, str]:
    """主执行函数，保证未预期异常也能生成运行概况"""
    global last_report
    report = RunReport()
    last_report = report
    http.cookies.clear()
    try:
        return _main(report)
    except Exception as e:
        detail = exception_detail(e)
        log.exception("主流程出现未预期错误")
        report.set("主流程", "failed", detail)
        return StatusCode.FAILURE.value, f"{report.render()}\n脚本执行出现未预期错误：{detail}"
    finally:
        http.cookies.clear()


def _main(report: RunReport) -> Tuple[int, str]:
    """实际执行流程"""
    check_github_actions()

    try:
        success, msg = initialize_config()
    except Exception as e:
        report.set("配置初始化", "failed", exception_detail(e))
        raise
    if not success:
        report.set("配置初始化", "failed", msg)
        return StatusCode.FAILURE.value, f"{report.render()}\n{msg}"
    report.set("配置初始化", "success")

    return_data = []
    errors = []
    section_success = 0

    def run_section(section_name: str, func) -> str:
        """执行单个模块，异常不会影响其他模块"""
        nonlocal section_success
        report.set(section_name, "running")
        before_errors = len(errors)
        try:
            result = func()
        except (CookieError, StokenError) as e:
            detail = exception_detail(e)
            message = f"{section_name}：{detail}"
            log.error(message)
            errors.append(message)
            report.set(section_name, "failed", detail)
            return ""
        except Exception as e:
            detail = exception_detail(e)
            message = f"{section_name}：{detail}"
            log.exception(f"{section_name}执行出现异常")
            errors.append(message)
            report.set(section_name, "failed", detail)
            return ""
        section_success += 1
        new_errors = errors[before_errors:]
        if new_errors:
            report.set(section_name, "partial", "；".join(new_errors))
        else:
            report.set(section_name, "success")
        return result or ""

    # 登录失败不应阻塞使用 Cookie / 云游戏 Token 的其他任务
    try:
        handle_login()
    except Exception as e:
        detail = exception_detail(e)
        message = f"登录：{detail}"
        log.exception("登录流程出现异常，将跳过登录并继续执行其他任务")
        errors.append(message)
        report.set("登录", "failed", detail)
    else:
        report.set("登录", "success")

    if config.config["account"]["cookie"] == "CookieError":
        message = "账号 Cookie 异常，依赖 Cookie 的任务可能失败"
        log.error(message)
        errors.append(message)
        current = report.items["登录"]
        detail = "账号 Cookie 异常"
        if current["status"] == "failed" and current["detail"]:
            detail = f"{current['detail']}；{detail}"
        report.set("登录", current["status"] if current["status"] == "failed" else "partial", detail)

    # 各模块独立执行，单个模块的网络异常不会中断后续任务
    if config.config["mihoyobbs"]["enable"]:
        result = run_section("米游社", lambda: run_mihoyobbs(errors))
        if result:
            return_data.append(result)
    else:
        report.set("米游社", "skipped")

    if config.config["games"]['cn']["enable"]:
        result = run_section("国服游戏签到", lambda: gamecheckin.run_task(errors))
        if result:
            return_data.append(result)
    else:
        report.set("国服游戏签到", "skipped")

    if config.config["cloud_games"]['cn']["enable"]:
        log.info("正在进行云游戏签到")
        result = run_section("国服云游戏签到", lambda: cloudgames.run_task(errors))
        if result:
            return_data.append(result)
    else:
        report.set("国服云游戏签到", "skipped")

    if config.config["games"]['os']["enable"]:
        log.info("海外版：")
        result = run_section("国际服游戏签到", lambda: hoyo_checkin.run_task(errors))
        if result:
            return_data.append(f"海外版：{result}")
    else:
        report.set("国际服游戏签到", "skipped")

    if config.config["cloud_games"]['os']["enable"]:
        log.info("正在进行云游戏国际版签到")
        result = run_section("国际服云游戏签到", lambda: os_cloudgames.run_task(errors))
        if result:
            return_data.append(result)
    else:
        report.set("国际服云游戏签到", "skipped")

    if config.config["web_activity"]['enable']:
        result = run_section("网页活动", lambda: run_web_activity(errors))
        if result:
            return_data.append(result)
    else:
        report.set("网页活动", "skipped")

    if errors:
        return_data.append("执行异常：\n" + "\n".join(f"- {err}" for err in errors))

    status_code = StatusCode.SUCCESS.value
    if errors:
        status_code = (StatusCode.FAILURE.value if section_success == 0
                       else StatusCode.PARTIAL_FAILURE.value)
    elif "触发验证码" in "\n".join(return_data):
        status_code = StatusCode.CAPTCHA_TRIGGERED.value

    detail_text = "\n".join(filter(None, return_data))
    return status_code, "\n".join(filter(None, [report.render(), detail_text]))


def task_run() -> None:
    """任务运行入口，任何失败都会尝试发送运行概况"""
    global last_report
    last_report = RunReport()
    message = ""

    try:
        status_code, message = main()
        push_message = message
    except CookieError as e:
        status_code = StatusCode.FAILURE.value
        push_message = f"{format_last_report()}\n账号 Cookie 出错！{exception_detail(e)}\n{message}"
        log.error("账号 Cookie 有问题！")
    except StokenError as e:
        status_code = StatusCode.FAILURE.value
        push_message = f"{format_last_report()}\n账号 Stoken 出错！{exception_detail(e)}\n{message}"
        log.error("账号 Stoken 有问题！")
    except Exception as e:
        status_code = StatusCode.FAILURE.value
        push_message = f"{format_last_report()}\n脚本执行出现未预期错误：{exception_detail(e)}"
        log.exception("脚本执行出现未预期错误")

    try:
        if push.push(status_code, push_message) != 0:
            log.warning("推送未成功，请检查 push.ini 中的邮件/推送配置")
    except Exception:
        log.exception("推送执行出现未预期错误")


if __name__ == "__main__":
    task_run()
