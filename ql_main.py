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
    if os.getenv("AutoMihoyoBBS_push_project") == "1" and push is not None:
        try:
            if push.push(status_code, message) == 0:
                return
        except Exception:
            log.exception("项目推送执行异常，尝试使用青龙通知")
    if notify is not None:
        try:
            notify.send(title, message)
            return
        except Exception:
            log.exception("青龙通知发送异常")
    else:
        log.warning("未找到青龙 notify 模块，且项目推送未成功，无法发送通知")


try:
    from main import main
    from main_multi import main_multi
except (ImportError, NameError) as e:
    ql_push(-99, "「米游社脚本」依赖缺失", f"依赖缺失：{e}，请更新青龙拉取范围")
    print("依赖缺失", e)
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
    except CookieError:
        title = "米游社-Cookie错误"
        message = "账号Cookie出错！"
        log.error("账号Cookie有问题！")
    except StokenError:
        title = "米游社-Stoken错误"
        message = "账号Stoken出错！"
        log.error("账号Stoken有问题！")
    except Exception as e:
        log.exception("脚本执行出现未预期错误")
        status_code = 1
        message = f"脚本执行出现未预期错误：{type(e).__name__}: {e}"
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
