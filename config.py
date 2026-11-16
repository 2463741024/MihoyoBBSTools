import os

import yaml
from copy import deepcopy

from error import ConfigError
from loghelper import log

# 这个字段现在还没找好塞什么地方好，就先塞config这里了
serverless = False
# 提示需要更新config版本
update_config_need = False

config = {
    'enable': True, 'version': 15, "push": "",
    'account': {'cookie': '', 'stuid': '', 'stoken': '', 'mid': ''},
    'device': {'name': 'Xiaomi MI 6', 'model': 'Mi 6', 'id': '', 'fp': ''},
    'mihoyobbs': {
        'enable': True, 'checkin': True, 'checkin_list': [5, 2],
        'read': True, 'like': True, 'cancel_like': True, 'share': True
    },
    'games': {
        'cn': {
            'enable': True,
            'useragent': 'Mozilla/5.0 (Linux; Android 12; Unspecified Device) AppleWebKit/537.36 (KHTML, like Gecko) '
                         'Version/4.0 Chrome/103.0.5060.129 Mobile Safari/537.36',
            'retries': 3,
            'genshin': {'checkin': True, 'black_list': []},
            'honkai2': {'checkin': False, 'black_list': []},
            'honkai3rd': {'checkin': False, 'black_list': []},
            'tears_of_themis': {'checkin': False, 'black_list': []},
            'honkai_sr': {'checkin': False, 'black_list': []},
            'zzz': {'checkin': False, 'black_list': []}
        },
        'os': {
            'enable': False, 'cookie': '', 'lang': 'zh-cn',
            'genshin': {'checkin': False, 'black_list': []},
            'honkai3rd': {'checkin': False, 'black_list': []},
            'tears_of_themis': {'checkin': False, 'black_list': []},
            'honkai_sr': {'checkin': False, 'black_list': []},
            'zzz': {'checkin': False, 'black_list': []}
        }
    },
    'cloud_games': {
        "cn": {
            "enable": False,
            "genshin": {'enable': False, 'token': ""},
            "zzz": {'enable': False, 'token': ""}
        },
        "os": {
            "enable": False, 'lang': 'zh-cn',
            "genshin": {'enable': False, 'token': ""}
        }
    },
    'competition': {
        'enable': False,
        'genius_invokation': {'enable': False, 'account': [], 'checkin': False, 'weekly': False}
    },
    'web_activity': {'enable': False, 'activities': []}
}
config_raw = deepcopy(config)

path = os.path.dirname(os.path.realpath(__file__)) + "/config"
if os.getenv("AutoMihoyoBBS_config_path") is not None:
    path = os.getenv("AutoMihoyoBBS_config_path")
config_prefix = os.getenv("AutoMihoyoBBS_config_prefix")
if config_prefix is None:
    # 多用户模式下默认使用 mhy_ 前缀，与青龙面板文档保持一致
    config_prefix = "mhy_" if os.getenv("AutoMihoyoBBS_config_multi") == "1" else ""
config_Path = f"{path}/{config_prefix}config.yaml"


def copy_config():
    return deepcopy(config_raw)


def merge_default_config(defaults: dict, data: dict) -> dict:
    """用默认配置补全缺失项，保证旧版/不完整的配置文件不会导致 KeyError"""
    if not isinstance(data, dict):
        return deepcopy(defaults)
    merged = deepcopy(defaults)
    for key, value in data.items():
        if value is None:
            # 配置项留空时回退到默认值，避免后续代码对 None 做迭代/取值
            continue
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_default_config(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def config_v11_update(data: dict):
    global update_config_need
    update_config_need = True
    old_cloud_games = data.get('cloud_games') or {}
    old_genshin = old_cloud_games.get('genshin') or {}
    new_config = {}
    for key in data:
        if key == "account":
            new_config["push"] = ""
        if key == "cloud_games":
            new_config['cloud_games'] = deepcopy(config_raw['cloud_games'])
            continue
        new_config[key] = deepcopy(data[key])
    new_config.setdefault('cloud_games', deepcopy(config_raw['cloud_games']))
    new_config['cloud_games']['cn']['enable'] = old_genshin.get('enable', False)
    new_config['cloud_games']['cn']['genshin']['enable'] = old_genshin.get('enable', False)
    new_config['cloud_games']['cn']['genshin']['token'] = old_genshin.get('token', "")
    new_config['version'] = 13
    log.info("config 已升级到：13")
    return new_config


def config_v12_update(data: dict):
    global update_config_need
    update_config_need = True
    data['version'] = 13
    cloud_games = data.setdefault('cloud_games', deepcopy(config_raw['cloud_games']))
    cloud_games.setdefault('cn', deepcopy(config_raw['cloud_games']['cn']))
    cloud_games['cn'].setdefault('zzz', {'enable': False, 'token': ""})
    log.info("config 已升级到: 13")
    return data


def config_v13_update(data: dict):
    global update_config_need
    update_config_need = True
    new_config = deepcopy(data)

    # 确保版本号更新为14
    new_config['version'] = 14
    new_config.setdefault('device', {}).setdefault('fp', '')

    log.info("config 已升级到：14")
    return new_config


def update_v14_update(data: dict):
    global update_config_need
    update_config_need = True
    new_config = deepcopy(data)
    new_config['version'] = 15
    new_config.setdefault('web_activity', {'enable': False, 'activities': []})
    log.info("config 已升级到：15")
    return new_config


def load_config(p_path=None):
    global config, update_config_need
    if not p_path:
        p_path = config_Path
    try:
        with open(p_path, "r", encoding='utf-8') as f:
            data = yaml.load(f, Loader=yaml.FullLoader)
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在：{p_path}，请复制 config.yaml.example 并重命名为 config.yaml") from exc
    except IsADirectoryError as exc:
        raise ConfigError(f"配置文件路径无效：{p_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"配置文件格式错误：{p_path}") from exc
    except OSError as exc:
        raise ConfigError(f"配置文件读取失败：{p_path}：{exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"配置文件内容为空或格式错误：{p_path}")

    raw_version = data.get('version', 0)
    try:
        version = int(raw_version)
    except (TypeError, ValueError):
        version = 0
    if version != config_raw['version']:
        if version == 11:
            data = config_v11_update(data)
        if data.get('version') == 12:
            data = config_v12_update(data)
        if data.get('version') == 13:
            data = config_v13_update(data)
        if data.get('version') == 14:
            data = update_v14_update(data)
        if data.get('version') != config_raw['version']:
            log.warning(f"未知的 config 版本：{raw_version}，将按默认配置补全缺失项")
            update_config_need = True
            data['version'] = config_raw['version']

    # 用默认配置补全缺失项，避免旧版配置缺少新字段时崩溃
    data = merge_default_config(config_raw, data)
    # 去除cookie最末尾的空格
    data["account"]["cookie"] = str(data["account"]["cookie"]).rstrip(' ')
    config = data
    if version != config_raw['version']:
        save_config(p_path=p_path, p_config=data)
    log.info("Config 加载完毕")
    return data


def save_config(p_path=None, p_config=None):
    global serverless
    if serverless:
        log.info("云函数执行，无法保存")
        return None
    if not p_path:
        p_path = config_Path
    if not p_config:
        p_config = config
    try:
        with open(p_path, "w+", encoding='utf-8') as f:
            f.seek(0)
            f.truncate()
            f.write(yaml.dump(p_config, Dumper=yaml.Dumper, sort_keys=False, allow_unicode=True))
            f.flush()
    except OSError:
        serverless = True
        log.info("配置保存失败，配置文件可能为只读")
    else:
        log.info("Config 保存完毕")


def clear_stoken():
    global config
    if serverless:
        log.info("云函数执行，无法保存")
        return None
    config["account"]["mid"] = ""
    config["account"]["stuid"] = ""
    config["account"]["stoken"] = "StokenError"
    log.info("Stoken 已删除")
    save_config()


def clear_cookie():
    global config
    if serverless:
        log.info("云函数执行，无法保存")
        return None
    config["account"]["cookie"] = "CookieError"
    log.info("Cookie 已删除")
    save_config()


def disable_games(region: str = "cn"):
    global config
    if serverless:
        log.info("云函数执行，无法保存")
        return None
    config['games'][region]['enable'] = False
    log.info(f"游戏签到（{region}）已关闭")
    save_config()


def clear_cookie_cloudgame_genshin():
    global config
    if serverless:
        log.info("云函数执行，无法保存")
        return None
    config['cloud_games']['cn']['genshin']["enable"] = False
    config['cloud_games']['cn']['genshin']['token'] = ""
    log.info("国服云原神 Cookie 删除完毕")
    save_config()


def clear_cookie_cloudgame_genshin_os():
    global config
    if serverless:
        log.info("云函数执行，无法保存")
        return None
    config['cloud_games']['os']['genshin']["enable"] = False
    config['cloud_games']['os']['genshin']['token'] = ""
    log.info("国际服云原神 Cookie 删除完毕")
    save_config()


def clear_cookie_cloudgame_zzz():
    global config
    if serverless:
        log.info("云函数执行，无法保存")
        return None
    config['cloud_games']['cn']['zzz']["enable"] = False
    config['cloud_games']['cn']['zzz']['token'] = ""
    log.info("国服云绝区零 Cookie 删除完毕")
    save_config()


if __name__ == "__main__":
    # 初始化配置文件
    # try:
    #     account_cookie = config['account']['cookie']
    #     config = load_config()
    #     config['account']['cookie'] = account_cookie
    # except OSError:
    #     pass
    # save_config()
    # update_config()
    pass
