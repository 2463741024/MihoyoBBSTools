import config
from loghelper import log


def run_task():
    """根据配置执行网页活动任务"""
    if not config.config.get('web_activity', {}).get('enable', False):
        log.info("网页活动功能未启用")
        return

    activities = config.config.get('web_activity', {}).get('activities', [])
    if not isinstance(activities, list):
        log.warning("网页活动配置格式错误，activities 应为列表")
        return
    if not activities:
        log.info("未配置需要执行的网页活动")
        return

    log.info(f"开始执行网页活动: {activities}")

    for activity in activities:
        try:
            # 检查是否有对应的函数
            func = globals().get(activity)
            if func and callable(func) and activity != "run_task":
                log.info(f"开始执行活动: {activity}")
                func()
                log.info(f"活动 {activity} 执行完成")
            else:
                log.warning(f"未找到活动函数: {activity}")
        except Exception as e:
            log.error(f"执行活动 {activity} 时出错: {str(e)}")
