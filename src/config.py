# -*- coding: utf-8 -*-
import os

import configparser

from log import logger


class Config(object):

    def __init__(self, config_file='../config.ini'):
        self._path = os.path.join(os.getcwd(), config_file)
        if not os.path.exists(self._path):
            raise FileNotFoundError("No such file: config.ini")
        self._config = configparser.ConfigParser()
        self._config.read(self._path, encoding='utf-8')
        select_mode = self._config.getint('config', 'select_mode')
        if not select_mode:
            select_mode = 1
        self.select_mode = select_mode

        # 加载商品配置

        sku_id = self.get('product', 'sku_id')
        if not sku_id:
            logger.error('请配置sku_id')
            exit(-1)
        self.sku_id = sku_id
        buy_time = self.get('product', 'buy_time')
        if not buy_time:
            logger.error('请配置buy_time')
            exit(-1)
        self.buy_time = buy_time

        # 加载配置
        retry = self._config.getint('config', 'retry')
        if not retry:
            retry = 5
        self.retry = retry
        interval = self._config.getfloat('config', 'interval')
        if not interval:
            interval = 0.5
        self.interval = interval
        num = self._config.getint('config', 'num')
        if not num:
            num = 1
        self.num = num
        sleep_interval = self._config.getint('config', 'sleep_interval')
        if not sleep_interval:
            sleep_interval = 1
        self.sleep_interval = sleep_interval
        fast_sleep_interval = self._config.getfloat('config', 'fast_sleep_interval')
        if not fast_sleep_interval:
            fast_sleep_interval = 0.01
        self.fast_sleep_interval = fast_sleep_interval
        is_risk_control = self.getboolean('config', 'is_risk_control')
        if not is_risk_control:
            is_risk_control = False
        self.is_risk_control = is_risk_control
        fast_mode = self.getboolean('config', 'fast_mode')
        if not fast_mode:
            fast_mode = True
        self.fast_mode = fast_mode

        # 加载模式配置
        if select_mode == 1:
            sku_buy_time = self.get('mode', 'sku_buy_time')
            if not sku_buy_time:
                logger.error('请配置sku_buy_time')
                exit(-1)
            self.sku_buy_time = sku_buy_time
            retry_interval = self._config.getfloat('mode', 'retry_interval')
            if not retry_interval:
                retry_interval = 0.2
            self.retry_interval = retry_interval
        elif select_mode == 2:
            is_pass_cart = self.getboolean('mode', 'is_pass_cart')
            if not is_pass_cart:
                is_pass_cart = False
            self.is_pass_cart = is_pass_cart
        else:
            logger.error('配置select_mode错误')
            exit(-1)

    def get(self, section, name, strip_blank=True, strip_quote=True):
        s = self._config.get(section, name)
        if strip_blank:
            s = s.strip()
        if strip_quote:
            s = s.strip('"').strip("'")

        return s

    def getboolean(self, section, name):
        return self._config.getboolean(section, name)


global_config = Config()
