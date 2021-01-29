# -*- coding:utf-8 -*-
import json
import os
import platform
import time
from datetime import datetime, timedelta

import requests

from log import logger


class Timer(object):

    def __init__(self, buy_time, sleep_interval=1, fast_sleep_interval=0.01, is_sync=True):

        # 同步京东服务器时间
        if is_sync is True:
            Timer.setSystemTime()

        # '2018-09-28 22:45:50.000'
        self.buy_time = datetime.strptime(buy_time, "%Y-%m-%d %H:%M:%S.%f")
        self.fast_buy_time = self.buy_time + timedelta(seconds=-3)
        self.connect_time = self.buy_time + timedelta(seconds=-3)
        self.sleep_interval = sleep_interval
        self.fast_sleep_interval = fast_sleep_interval

    def start(self, sock_conn_func=None):
        logger.info('正在等待到达设定时间：%s' % self.buy_time)
        is_connected = False
        now_time = time.time
        buy_time_timestamp = self.buy_time.timestamp()
        fast_buy_time_timestamp = self.fast_buy_time.timestamp()
        # connect_time_timestamp = self.connect_time.timestamp()
        fast_sleep_interval = self.fast_sleep_interval
        sleep_interval = self.sleep_interval
        while True:
            if now_time() > buy_time_timestamp:
                logger.info('时间到达，开始执行')
                break
            else:
                if now_time() > fast_buy_time_timestamp:
                    if is_connected:
                        time.sleep(fast_sleep_interval)
                    else:
                        # if now_time() > connect_time_timestamp and sock_conn_func is not None:
                        if sock_conn_func is not None:
                            sock_conn_func()
                            is_connected = True
                else:
                    # TODO 保活
                    time.sleep(sleep_interval)

    @staticmethod
    def setSystemTime():
        url = 'https://a.jd.com//ajax/queryServerData.html'

        session = requests.session()

        # get server time
        t0 = datetime.now()
        ret = session.get(url).text
        t1 = datetime.now()

        js = json.loads(ret)
        t = float(js["serverTime"]) / 1000
        dt = datetime.fromtimestamp(t) + ((t1 - t0) / 2)

        sys = platform.system()
        if sys == "Windows":
            import win_util
            win_util.setWinSystemTime(dt)
        elif sys == "Linux":
            try:
                os.system(f'date -s "{dt.strftime("%Y-%m-%d %H:%M:%S.%f000")}"')
                logger.info('已同步京东服务器时间：%s' % dt)
            except Exception as e:
                logger.error('同步京东服务器时间失败，请检查权限')
                logger.error(e)
