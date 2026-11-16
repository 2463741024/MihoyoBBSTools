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


class StatusCode(Enum):
    SUCCESS = 0
    FAILURE = 1
    PARTIAL_FAILURE = 2
    CAPTCHA_TRIGGERED = 3


def exception_message(error: Exception) -> str:
    """提取更友好的异常描述"""
    return str(getattr(error, "info", error))


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


def run_mihoyobbs() -> str:
    """执行米游社签到任务"""
    if not config.config["mihoyobbs"]["enable"]:
        return ""
    if config.config["account"]["stoken"] == "StokenError":
        raise StokenError("账号 Stoken 异常")
    return mihoyobbs.Mihoyobbs().run_task()


def run_web_activity(errors: list = None) -> str:
    """执行网页活动任务"""
    if not config.config["web_activity"]['enable']:
        return ""
    log.info("正在进行米游社网页活动任务")
    web_activity.run_task(errors)
    return ""


def main() -> Tuple[int, str]:
    """主执行函数"""
    check_github_actions()

    success, msg = initialize_config()
    if not success:
        return StatusCode.FAILURE.value, msg

    return_data = []
    errors = []
    section_success = 0

    def run_section(section_name: str, func) -> str:
        """执行单个模块，异常不会影响其他模块"""
        nonlocal section_success
        try:
            result = func()
        except (CookieError, StokenError) as e:
            message = f"{section_name}：{exception_message(e)}"
            log.error(message)
            errors.append(message)
            return ""
        except Exception as e:
            message = f"{section_name}：{type(e).__name__}: {e}"
            log.exception(f"{section_name}执行出现异常")
            errors.append(message)
            return ""
        section_success += 1
        return result or ""

    # 登录失败不应阻塞使用 Cookie / 云游戏 Token 的其他任务
    try:
        handle_login()
    except Exception as e:
        message = f"登录：{type(e).__name__}: {exception_message(e)}"
        log.exception("登录流程出现异常，将跳过登录并继续执行其他任务")
        errors.append(message)

    if config.config["account"]["cookie"] == "CookieError":
        message = "账号 Cookie 异常，依赖 Cookie 的任务可能失败"
        log.error(message)
        errors.append(message)

    # 各模块独立执行，单个模块的网络异常不会中断后续任务
    if config.config["mihoyobbs"]["enable"]:
        result = run_section("米游社", run_mihoyobbs)
        if result:
            return_data.append(result)

    if config.config["games"]['cn']["enable"]:
        result = run_section("国服游戏签到", lambda: gamecheckin.run_task(errors))
        if result:
            return_data.append(result)

    if config.config["cloud_games"]['cn']["enable"]:
        log.info("正在进行云游戏签到")
        result = run_section("国服云游戏签到", lambda: cloudgames.run_task(errors))
        if result:
            return_data.append(result)

    if config.config["games"]['os']["enable"]:
        log.info("海外版：")
        result = run_section("国际服游戏签到", lambda: hoyo_checkin.run_task(errors))
        if result:
            return_data.append(f"海外版：{result}")

    if config.config["cloud_games"]['os']["enable"]:
        log.info("正在进行云游戏国际版签到")
        result = run_section("国际服云游戏签到", lambda: os_cloudgames.run_task(errors))
        if result:
            return_data.append(result)

    if config.config["web_activity"]['enable']:
        result = run_section("网页活动", lambda: run_web_activity(errors))
        if result:
            return_data.append(result)

    if errors:
        return_data.append("执行异常：\n" + "\n".join(f"- {err}" for err in errors))

    status_code = StatusCode.SUCCESS.value
    if errors:
        status_code = (StatusCode.FAILURE.value if section_success == 0
                       else StatusCode.PARTIAL_FAILURE.value)
    elif "触发验证码" in "\n".join(return_data):
        status_code = StatusCode.CAPTCHA_TRIGGERED.value

    return status_code, "\n".join(filter(None, return_data))


def task_run() -> None:
    """任务运行入口"""
    message = ""

    try:
        status_code, message = main()
        push_message = message
    except CookieError:
        status_code = StatusCode.FAILURE.value
        push_message = f"账号 Cookie 出错！\n{message}"
        log.error("账号 Cookie 有问题！")
    except StokenError:
        status_code = StatusCode.FAILURE.value
        push_message = f"账号 Stoken 出错！\n{message}"
        log.error("账号 Stoken 有问题！")
    except Exception as e:
        status_code = StatusCode.FAILURE.value
        push_message = f"脚本执行出现未预期错误：{e}"
        log.exception("脚本执行出现未预期错误")

    try:
        push.push(status_code, push_message)
    except Exception:
        log.exception("推送执行出现未预期错误")


if __name__ == "__main__":
    task_run()
