"""
new Env('米游社');
"""
import os
from loghelper import log
from error import CookieError, StokenError

try:
    import notify
except ImportError:
    # 部分青龙镜像不提供 notify 模块，降级到项目自带推送
    notify = None

try:
    import push
except ImportError:
    # PyYAML 等依赖缺失时仍允许通过青龙通知报告依赖问题
    push = None


def ql_push(status_code, title, message):
    message = str(message)
    project_attempted = False
    # 未安装 notify 时也必须尝试项目自带推送，否则失败邮件会丢失
    if os.getenv("AutoMihoyoBBS_push_project") == "1" or notify is None:
        project_attempted = True
        if push is not None:
            try:
                if push.push(status_code, message) == 0:
                    return
            except Exception:
                log.exception("项目推送执行异常")
    notify_sent = False
    if notify is not None:
        try:
            notify.send(title, message)
            notify_sent = True
        except Exception:
            log.exception("青龙通知发送异常")
    # 失败时即使青龙通知成功也额外尝试项目推送；青龙通知失败时同样回退项目推送
    if not project_attempted and push is not None and (status_code != 0 or not notify_sent):
        try:
            if push.push(status_code, message) == 0:
                return
        except Exception:
            log.exception("项目推送执行异常")
    if notify_sent:
        return
    log.warning("通知发送失败：青龙 notify 与项目推送均不可用")


try:
    from main import main, format_last_report
    from main_multi import main_multi
except Exception as e:
    ql_push(-99, "「米游社脚本」依赖缺失", f"脚本加载失败：{e}，请检查依赖和青龙拉取范围")
    print("脚本加载失败", e)
    exit(-1)


def single():
    title = "米游社"
    status_code = 1
    message = "脚本执行失败"
    try:
        status_code, message = main()
        if status_code == 1:
            title = "米游社-执行失败"
        elif status_code == 2:
            title = "米游社-部分任务失败"
        elif status_code == 3:
            title = "米游社-触发验证码"
    except CookieError as e:
        title = "米游社-Cookie错误"
        message = f"{format_last_report()}\n账号Cookie出错！{e}"
        log.error("账号Cookie有问题！")
    except StokenError as e:
        title = "米游社-Stoken错误"
        message = f"{format_last_report()}\n账号Stoken出错！{e}"
        log.error("账号Stoken有问题！")
    except Exception as e:
        log.exception("脚本执行出现未预期错误")
        status_code = 1
        message = f"{format_last_report()}\n脚本执行出现未预期错误：{type(e).__name__}: {e}"
    ql_push(status_code, title, message)


def multi():
    try:
        status_code, message = main_multi(True)
    except Exception as e:
        log.exception("多用户任务执行出现未预期错误")
        status_code = 1
        message = f"脚本执行出现未预期错误：{type(e).__name__}: {e}"
    title = "米游社"
    if status_code == 1:
        title = "米游社-全部配置错误"
        log.error("全部配置文件错误！请检查配置文件！")
    elif status_code == 2:
        title = "米游社-部分配置错误"
        log.error("部分配置文件错误，请检查配置文件")
    elif status_code == 3:
        title = "米游社-触发验证码"
    ql_push(status_code, title, message)


if __name__ == "__main__":
    if os.getenv("AutoMihoyoBBS_config_multi") == "1":
        multi()
    else:
        single()
