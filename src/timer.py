# -*- coding:utf-8 -*-

# import gevent
# from gevent import monkey; monkey.patch_all()
import threading
import json
import os
import platform
import random
import time
from datetime import datetime, timedelta

import requests

from log import logger


class Timer(object):

    def __init__(self, buy_time, sleep_interval=1, fast_sleep_interval=0.01, is_sync=True, assistant=None):

        # 同步京东服务器时间
        if is_sync is True:
            Timer.setSystemTime()

        # '2018-09-28 22:45:50.000'
        self.buy_time = datetime.strptime(buy_time, "%Y-%m-%d %H:%M:%S.%f")
        self.fast_buy_time = self.buy_time + timedelta(seconds=-3)
        self.connect_time = self.buy_time + timedelta(seconds=-20)
        self.sleep_interval = sleep_interval
        self.fast_sleep_interval = fast_sleep_interval
        self.buy_time_timestamp = self.buy_time.timestamp()
        self.fast_buy_time_timestamp = self.fast_buy_time.timestamp()
        self.connect_time_timestamp = self.connect_time.timestamp()
        self.is_connected = False
        self.now_time = time.time
        self.assistant = assistant
        self.fast_mode = assistant.config.fast_mode
        if self.fast_mode:
            assistant.make_seckill_connect()

    def start(self):
        logger.info('正在等待到达设定时间：%s' % self.buy_time)
        check_timestamp = None
        assistant = self.assistant
        buy_time_timestamp = self.buy_time.timestamp()
        fast_buy_time_timestamp = self.fast_buy_time.timestamp()
        connect_time_timestamp = self.connect_time.timestamp()
        fast_sleep_interval = self.fast_sleep_interval
        sleep_interval = self.sleep_interval
        while True:
            now = self.now_time()
            if now > buy_time_timestamp:
                # 临时修改，默认开启并发
                break
                # logger.info('时间超出，开始执行')
                # self.assistant.start_func()
                # return None
            else:
                if now > fast_buy_time_timestamp:
                    if self.is_connected:
                        time.sleep(fast_sleep_interval)
                    else:
                        # if now_time() > connect_time_timestamp and sock_conn_func is not None:
                        if self.fast_mode:
                            assistant.connect_now()
                            self.is_connected = True
                elif now > connect_time_timestamp:
                    if not self.is_connected and self.fast_mode:
                        assistant.connect_now()
                        self.is_connected = True
                        logger.info('时间接近，开启%s并发倒计时', assistant.concurrent_count)
                        break
                else:
                    # 保活
                    if self.fast_mode:
                        if check_timestamp is None:
                            check_timestamp = now + 1800 + random.randint(-10, 10)
                        elif now > check_timestamp:
                            if assistant._validate_cookies() is True:
                                check_timestamp = None
                                logger.info("账户在线状态检查正常")
                            else:
                                logger.error("账户已离线，请重新登录！")
                                exit(-1)
                    time.sleep(sleep_interval)
        # 开启协程
        # for i in range(assistant.concurrent_count):
        #     assistant.concurrent_gevent_array.append(gevent.spawn(self.ready_call))
        # gevent.joinall(assistant.concurrent_gevent_array)
        # 开启线程
        thread_list = []
        for i in range(assistant.concurrent_count):
            t = threading.Thread(target=self.ready_call)
            t.start()
            thread_list.append(t)
        for t in thread_list:
            t.join()

    def ready_call(self):
        while True:
            now = self.now_time()
            if now > self.buy_time_timestamp:
                logger.info('时间到达，开始执行')
                self.assistant.start_func()
                break
            else:
                if self.is_connected:
                    time.sleep(self.fast_sleep_interval)
                else:
                    # if now_time() > connect_time_timestamp and sock_conn_func is not None:
                    if self.fast_mode:
                        self.is_connected = True
                        self.assistant.connect_now()

    @staticmethod
    def setSystemTime():
        url = 'https://a.jd.com//ajax/queryServerData.html'

        try:
            session = requests.session()

            # get server time
            t0 = datetime.now()
            ret = session.get(url).text
            t1 = datetime.now()

            if not ret:
                logger.error('同步京东服务器时间失败，时间同步接口已失效')
                return
            js = json.loads(ret)
            t = float(js["serverTime"]) / 1000
            dt = datetime.fromtimestamp(t) + ((t1 - t0) / 2)

            sys = platform.system()
            if sys == "Windows":
                import win_util
                win_util.setWinSystemTime(dt)
            elif sys == "Linux":
                os.system(f'date -s "{dt.strftime("%Y-%m-%d %H:%M:%S.%f000")}"')
                logger.info('已同步京东服务器时间：%s' % dt)
        except Exception as e:
            logger.error('同步京东服务器时间失败，请检查权限')
            logger.error(e)
