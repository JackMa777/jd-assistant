# -*- coding: utf-8 -*-
import os

import configparser


class Config(object):

    def __init__(self, config_file='../config.ini'):
        self._path = os.path.join(os.getcwd(), config_file)
        if not os.path.exists(self._path):
            raise FileNotFoundError("No such file: config.ini")
        self._config = configparser.ConfigParser()
        self._config.read(self._path, encoding='utf-8')

    def get(self, section, name, strip_blank=True, strip_quote=True):
        s = self._config.get(section, name)
        if strip_blank:
            s = s.strip()
        if strip_quote:
            s = s.strip('"').strip("'")

        return s

    def getboolean(self, section, name):
        return self._config.getboolean(section, name)


class CustomConfig(object):
    # 抢购通用配置
    sku_id = ''                 # 商品id
    buy_time = ''               # 开始抢购时间，格式：'2020-11-28 12:59:59.950'，建议设置提前0.050秒，如果网络慢可根据自己网络情况适当修改
    retry = 5                   # 抢购重复执行次数，可选参数，默认5次
    interval = 0.2              # 抢购执行间隔，可选参数，默认200毫秒
    num = 1                     # 购买数量，可选参数，默认1个
    sleep_interval = 0.5        # 抢购前倒计时轮询时间，默认0.5秒
    fast_sleep_interval = 0.01  # 抢购5秒内倒计时轮询时间，默认0.01秒
    is_risk_control = False     # 账号是否被风控，默认False
    fast_mode = False            # 如果帐号没被风控，可启用快速抢购模式，可一定程度提高抢购成功率，默认True

    # 配置【预约抢购，自动加入购物车】
    # 注意：一定要在抢购开始前手动清空购物车中此类无法勾选的商品！（因为脚本在执行清空购物车操作时，无法清空不能勾选的商品）
    is_pass_cart = False        # 是否跳过添加购物车，默认False

global_config = Config()
