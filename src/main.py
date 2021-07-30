#!/usr/bin/env python
# -*- coding:utf-8 -*-

from jd_assistant import Assistant

if __name__ == '__main__':
    """
    启动前请先【安装chrome】并下载【与内核版本相同的chromedriver】，然后在config.ini中配置chromedriver_path
    如果需要指定chrome路径，则需要配置chrome_path
    chromedriver下载：https://sites.google.com/a/chromium.org/chromedriver/home
    """

    asst = Assistant(True)  # 初始化
    if asst.use_new:
        asst.login_by_browser()
    else:
        asst.login_by_QRcode()  # 扫码登陆

    asst.start_by_config()

    # 根据商品是否有货自动下单
    # 6个参数：
    # sku_ids: 商品id。可以设置多个商品，也可以带数量，如：'1234' 或 '1234,5678' 或 '1234:2' 或 '1234:2,5678:3'
    # area: 地区id
    # wait_all: 是否等所有商品都有货才一起下单，可选参数，默认False
    # stock_interval: 查询库存时间间隔，可选参数，默认3秒
    # submit_retry: 提交订单失败后重试次数，可选参数，默认3次
    # submit_interval: 提交订单失败后重试时间间隔，可选参数，默认5秒
