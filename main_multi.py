import os
import sys
import main
import time
import push
import config
import random
from loghelper import log
from error import CookieError, StokenError, ConfigError


def find_config(*extensions: str) -> list:
    """按文件名顺序返回指定扩展名的配置文件。"""
    with os.scandir(config.path) as entries:
        return sorted(
            entry.name for entry in entries
            if entry.name.startswith(config.config_prefix)
            and os.path.splitext(entry.name)[1] in extensions
            and entry.is_file()
        )


def ql_config(config_list: list) -> list:
    """
    筛选青龙多用户配置文件（头部匹配）
    
    青龙面板的配置文件通常以 'mhy_' 开头，此函数用于筛选这些文件
    
    Args:
        config_list (list): 配置文件列表
    
    Returns:
        list: 青龙多用户配置文件列表
    """
    config_list_ql = []
    for files in config_list:
        if 'mhy_' == files[:4]:
            config_list_ql.append(files)
    return config_list_ql


def get_config_list() -> list:
    """
    获取所有可用的配置文件列表
    
    搜索 .yaml 和 .yml 文件，并根据环境变量判断是否使用青龙面板模式
    
    Returns:
        list: 配置文件列表
    """
    config_list = find_config('.yaml', '.yml')
    # 增强环境变量处理，添加更多的错误处理和默认值
    config_prefix = os.getenv("AutoMihoyoBBS_config_prefix")
    config_multi = os.getenv("AutoMihoyoBBS_config_multi", "0")
    ql_dir = os.getenv("QL_DIR")
    
    if config_prefix is None and config_multi == '1':
        # 判断通过读取青龙目录环境变量来判断用户是否使用青龙面板
        if ql_dir is not None:
            config_list = ql_config(config_list)
    if len(config_list) == 0:
        raise ConfigError("未检测到配置文件，请确认 config 文件夹存在 .yaml/.yml 后缀名的配置文件！")
    return config_list


def push_user_error(config_name: str, message: str) -> None:
    """发送单个配置的错误推送，推送失败不影响其他配置"""
    if not config.config.get("push", ""):
        return
    try:
        push.PushHandler(config.config["push"]).push(1, message)
    except Exception:
        log.exception(f"{config_name} 错误通知发送失败")


def main_multi(autorun: bool) -> tuple:
    """
    多用户模式主执行函数
    
    依次执行所有配置文件的任务，并汇总结果
    
    Args:
        autorun (bool): 是否自动运行，False 时会等待用户确认
    
    Returns:
        tuple: (状态码, 推送消息)
            状态码：
            0 - 全部成功
            1 - 全部失败
            2 - 部分失败
            3 - 有验证码触发
    """
    log.info("AutoMihoyoBBS Multi User mode")
    log.info("正在搜索配置文件！")
    config.update_config_need = False
    try:
        config_list = get_config_list()
    except (ConfigError, OSError) as e:
        log.error(str(e))
        return 1, str(e)
    if autorun:
        log.info(f"已搜索到 {len(config_list)} 个配置文件，正在开始执行！")
    else:
        log.info(f"已搜索到 {len(config_list)} 个配置文件，请确认是否无多余文件！\r\n{config_list}")
        try:
            input("请输入回车继续，需要重新搜索配置文件请 Ctrl+C 退出脚本")
        except KeyboardInterrupt:
            exit(0)
    original_path, original_config = config.config_Path, config.config
    update_needed = False
    results = {"ok": [], "close": [], "error": [], "captcha": []}
    error_details = []
    try:
        for index, name in enumerate(config_list):
            run_config(name, results, error_details)
            update_needed |= config.update_config_need
            if index < len(config_list) - 1:
                time.sleep(random.randint(3, 10))
    finally:
        config.config_Path = original_path
        config.config = original_config
        config.update_config_need = update_needed

    print("")
    push_message = f'脚本执行完毕，共执行{len(config_list)}个配置文件，成功{len(results["ok"])}个，' \
                   f'没执行{len(results["close"])}个，失败{len(results["error"])}个，' \
                   f'触发验证码{len(results["captcha"])}个' \
                   f'\r\n没执行的配置文件：{results["close"]}\r\n执行失败的配置文件：{results["error"]}\r\n' \
                   f'触发游戏签到验证码的配置文件：{results["captcha"]}'
    if error_details:
        push_message += "\r\n\r\n失败详情：\r\n" + "\r\n\r\n".join(error_details)
    log.info(push_message)
    if len(results["error"]) == len(config_list):
        return 1, push_message
    if results["error"]:
        return 2, push_message
    if results["captcha"]:
        return 3, push_message
    return 0, push_message


def run_config(name, results, error_details):
    log.info(f"正在执行 {name}")
    config.config_Path = os.path.join(config.path, name)
    try:
        run_code, run_message = main.main()
    except Exception as e:
        if isinstance(e, CookieError):
            message = "账号 Cookie 出错！"
        elif isinstance(e, StokenError):
            message = "账号 Stoken 有问题！"
        elif isinstance(e, ConfigError):
            message = f"配置文件有误：{e}"
        else:
            message = f"{type(e).__name__}: {e}"
            log.exception(f"{name} 执行出现未预期错误")
        push_user_error(name, message)
        run_code, run_message = 1, message
    if run_code in (1, 2):
        error_details.append(f"{name}：\n{run_message}")
    outcome = {0: "ok", 1: "error", 2: "error", 3: "captcha"}.get(run_code, "close")
    results[outcome].append(name)
    log.info(f"{name} 执行完毕")


if __name__ == "__main__":
    if (len(sys.argv) >= 2 and sys.argv[1] == "autorun") or os.getenv("AutoMihoyoBBS_autorun") == "1":
        autorun_flag = True
    else:
        autorun_flag = False
    task_status, task_push_message = main_multi(autorun_flag)
    # 使用 PushHandler 实例，保持与其他推送处理方式一致
    push_handler = push.PushHandler()
    push_handler.push(task_status, task_push_message)
    exit(0)
