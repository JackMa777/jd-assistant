# -*- coding:utf-8 -*-
import ctypes
import time

import win32api

from log import logger


def is_admin():
    try:
        # 获取当前用户的是否为管理员
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def setWinSystemTime(dt):
    if not is_admin():
        pass
        # exit(-1)
        # 重新运行这个程序使用管理员权限
        # ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
    tm_year, tm_mon, tm_mday, tm_hour, tm_min, tm_sec, tm_wday, tm_yday, tm_isdst = time.gmtime(
        time.mktime(dt.timetuple()))
    msec = dt.microsecond / 1000

    try:
        win32api.SetSystemTime(tm_year, tm_mon, tm_wday, tm_mday, tm_hour, tm_min, tm_sec, int(msec))
        logger.info('已同步京东服务器时间：%s' % dt)
    except Exception as e:
        logger.error('同步京东服务器时间失败，请检查权限')
        logger.error(e)
