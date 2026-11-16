import main
import push
import config
import main_multi
from error import CookieError, StokenError


def main_handler(event: dict, context: dict):
    config.serverless = True
    push_message = "脚本执行失败"
    try:
        status_code, push_message = main.main()
    except CookieError:
        status_code = 1
        push_message = "账号 Cookie 出错！"
    except StokenError:
        status_code = 1
        push_message = "账号 Stoken 出错！"
    except Exception as e:
        status_code = 1
        push_message = f"脚本执行出现未预期错误：{e}"
    push.push(status_code, push_message)
    print("云函数测试支持！")
    return 0


def main_handler_mulit(event: dict, context: dict):
    config.serverless = True
    try:
        # 多用户需要传递True表示自动执行，不需要手动进行确认
        status_code, push_message = main_multi.main_multi(True)
    except Exception as e:
        status_code, push_message = 1, f"脚本执行出现未预期错误：{e}"
    push.push(status_code, push_message)
    print("云函数多用户测试支持！")
    return 0
