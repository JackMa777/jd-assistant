#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import os
import pickle
import random
import re
import time
from datetime import datetime, timedelta
from urllib import parse

import requests
from bs4 import BeautifulSoup

import CustomBrowser
import address_util
from config import global_config
from exception import AsstException
from log import logger
from messenger import Messenger
from socketclient import SocketClient, util
from socketclient.utils import http_util
from socketclient.utils.http import cookie_util
from timer import Timer
from util import (
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    check_login,
    deprecated,
    encrypt_pwd,
    encrypt_payment_pwd,
    get_tag_value,
    get_random_useragent,
    open_image,
    parse_area_id,
    parse_json,
    parse_sku_id,
    parse_items_dict,
    response_status,
    save_image,
    split_area_id, DEFAULT_M_USER_AGENT, nested_parser, nested_inner_parser
)


class Assistant(object):

    def __init__(self, use_new=False):
        self.config = None
        self.backend_mod = util.load_backend('gevent')
        self.sem = self.backend_mod.Semaphore(1)
        self.event = self.backend_mod.Event()
        self.socket_client = SocketClient(backend=self.backend_mod)

        # 功能相关
        self.concurrent_gevent_array = []
        self.concurrent_count = global_config.concurrent_count
        self.start_func = None
        self.chromedriver_path = global_config.get('config', 'chromedriver_path')
        self.chrome_path = global_config.get('config', 'chrome_path')
        self.timeout = float(global_config.get('config', 'timeout') or DEFAULT_TIMEOUT)
        self.send_message = global_config.getboolean('messenger', 'enable')
        self.messenger = Messenger(global_config.get('messenger', 'sckey')) if self.send_message else None
        use_random_ua = global_config.getboolean('config', 'random_useragent')

        if use_new:
            self.user_agent = DEFAULT_M_USER_AGENT
        elif not use_random_ua:
            self.user_agent = DEFAULT_USER_AGENT
        else:
            self.user_agent = get_random_useragent()
        self.use_new = use_new
        self.br = None
        self.headers = {'User-Agent': self.user_agent}

        # 用户相关
        if use_new:
            self.data = dict()
        self.eid = global_config.get('config', 'eid')
        self.fp = global_config.get('config', 'fp')
        self.track_id = global_config.get('config', 'track_id')
        self.risk_control = global_config.get('config', 'risk_control')
        self.letterMap = ["Z", "A", "B", "C", "D", "E", "F", "G", "H", "I"]

        self.area_id = None

        self.item_zzz = dict()
        self.item_url_param = dict()

        self.item_cat = dict()
        self.item_vender_ids = dict()  # 记录商家id
        self.param_json = dict()  # 记录参数
        self.special_attrs = dict()

        # self.seckill_init_info = dict()
        # self.seckill_order_data = dict()
        # self.seckill_url = dict()

        self.item_requests = []
        self.item_requests.append(dict())
        self.item_requests.append(dict())
        self.item_requests.append(dict())
        self.item_requests.append(dict())
        self.item_requests.append(dict())
        self.item_requests.append(dict())
        self.item_requests.append(dict())
        self.item_requests.append(dict())
        self.item_requests.append(dict())
        self.item_requests.append(dict())
        self.item_requests.append(dict())

        self.username = ''
        self.nick_name = ''
        self.is_login = False
        self.sess = requests.session()
        self.cookies_str = None
        # 请求信息
        self.request_info = dict()
        try:
            self._load_cookies()
        except Exception:
            pass

        # 已登录则刷新cookies
        if self.is_login:
            self.nick_name = self.get_user_info()
            self._save_cookies()

    def init_browser(self, headless=True):
        br = self.br = CustomBrowser.CustomBrowser(self.user_agent, self.chromedriver_path, self.chrome_path, headless)
        count = 0
        # 启动浏览器
        while True:
            try:
                br.openUrl('chrome://version/')
            except Exception as e:
                logger.error(e)
                logger.error(f'无法初始化浏览器cookies，'
                             f'请检查config.ini文件中chromedriver_path与chrome_path的配置 或 检查网络代理是否关闭，开启代理会导致浏览器初始化失败')
                if count > 3:
                    if br:
                        br.quit()
                    logger.error('初始化浏览器cookies失败！'
                                 '请检查config.ini文件中chromedriver_path与chrome_path的配置 或 检查网络代理是否关闭，开启代理会导致浏览器初始化失败！')
                    exit(-1)
            else:
                break
            count += 1
            logger.info('初始化下单参数失败！开始第 %s 次重试', count)
        return br

    @property
    def seckill_url(self):
        return self.item_requests[0]

    @property
    def is_request_seckill_url(self):
        return self.item_requests[1]

    @property
    def seckill_init_info(self):
        return self.item_requests[2]

    @property
    def seckill_order_data(self):
        return self.item_requests[3]

    @property
    def is_seckill_checkout_page(self):
        return self.item_requests[4]

    @property
    def is_add_cart_request(self):
        return self.item_requests[5]

    @property
    def is_get_checkout_page(self):
        return self.item_requests[6]

    @property
    def get_submit_page_data(self):
        return self.item_requests[7]

    @property
    def get_promiseUuid(self):
        return self.item_requests[8]

    @property
    def get_submit_data(self):
        return self.item_requests[9]

    @property
    def get_submit_referer(self):
        return self.item_requests[10]

    def _load_cookies(self):
        cookies_file = ''
        for name in os.listdir('../cookies'):
            if name.endswith('.cookies'):
                cookies_file = '../cookies/{0}'.format(name)
                break
        with open(cookies_file, 'rb') as f:
            local_cookies = pickle.load(f)
        self.sess.cookies.update(local_cookies)
        self.is_login = self._validate_cookies()

    def _save_cookies(self):
        cookies_file = '../cookies/{0}.cookies'.format(self.nick_name)
        directory = os.path.dirname(cookies_file)
        if not os.path.exists(directory):
            os.makedirs(directory)
        with open(cookies_file, 'wb') as f:
            pickle.dump(self.sess.cookies, f)

    def _validate_cookies(self):
        """验证cookies是否有效（是否登陆）
        通过访问用户订单列表页进行判断：若未登录，将会重定向到登陆页面。
        :return: cookies是否有效 True/False
        """

        if self.use_new:
            url = 'https://wq.jd.com/user/info/GetUserAllPinInfo'
            # url = 'https://home.m.jd.com/myJd/home.action'
            # url = 'https://home.m.jd.com/userinfom/QueryUserInfoM'
            params = {
                'sceneval': 2,
                'g_login_type': 1,
                'callback': 'userInfoCallBack',
                'g_ty': 'ls',
                '_': str(int(time.time() * 1000))
            }
            try:
                resp = self.sess.get(url=url, params=params,
                                     headers={'dnt': '1', 'referer': 'https://wqs.jd.com/', 'sec-fetch-dest': 'script',
                                              'sec-fetch-mode': 'no-cors', 'sec-fetch-site': 'same-site',
                                              'user-agent': self.user_agent}, allow_redirects=False)
                if resp.status_code == requests.codes.OK:
                    html = resp.text
                    if html and 'pin' in html:
                        match = re.search(r'^try\{userInfoCallBack\((.*)\);\}catch\(e\)\{\}$', html)
                        if match:
                            json_str = match.group(1)
                            if json_str:
                                json_dict = json.loads(json_str)
                                self.nick_name = json_dict['userdata']['renderJDDate'][0]['msg']['nickname']
                                return True
            except Exception as e:
                logger.error(e)

            self.sess = requests.session()
            return False
        else:
            url = 'https://order.jd.com/center/list.action'
            # payload = {
            #     'rid': str(int(time.time() * 1000)),
            # }
            try:
                resp = self.sess.get(url=url,
                                     headers={'dnt': '1', 'sec-fetch-dest': 'document', 'sec-fetch-mode': 'navigate',
                                              'sec-fetch-site': 'none', 'upgrade-insecure-requests': '1',
                                              'user-agent': self.user_agent}, allow_redirects=False)
                if resp.status_code == requests.codes.OK:
                    return True
            except Exception as e:
                logger.error(e)

            self.sess = requests.session()
            return False

    @deprecated
    def _need_auth_code(self, username):
        url = 'https://passport.jd.com/uc/showAuthCode'
        data = {
            'loginName': username,
        }
        payload = {
            'version': 2015,
            'r': random.random(),
        }
        resp = self.sess.post(url, params=payload, data=data, headers=self.headers)
        if not response_status(resp):
            logger.error('获取是否需要验证码失败')
            return False

        resp_json = json.loads(resp.text[1:-1])  # ({"verifycode":true})
        return resp_json['verifycode']

    @deprecated
    def _get_auth_code(self, uuid):
        image_file = os.path.join(os.getcwd(), 'jd_authcode.jpg')

        url = 'https://authcode.jd.com/verify/image'
        payload = {
            'a': 1,
            'acid': uuid,
            'uid': uuid,
            'yys': str(int(time.time() * 1000)),
        }
        headers = {
            'User-Agent': self.user_agent,
            'Referer': 'https://passport.jd.com/uc/login',
        }
        resp = self.sess.get(url, params=payload, headers=headers)

        if not response_status(resp):
            logger.error('获取验证码失败')
            return ''

        save_image(resp, image_file)
        open_image(image_file)
        return input('验证码:')

    def _get_login_page(self):
        url = "https://passport.jd.com/new/login.aspx"
        page = self.sess.get(url, headers=self.headers)
        return page

    @deprecated
    def _get_login_data(self):
        page = self._get_login_page()
        soup = BeautifulSoup(page.text, "html.parser")
        input_list = soup.select('.form input')

        # eid & fp are generated by local javascript code according to browser environment
        return {
            'sa_token': input_list[0]['value'],
            'uuid': input_list[1]['value'],
            '_t': input_list[4]['value'],
            'loginType': input_list[5]['value'],
            'pubKey': input_list[7]['value'],
            'eid': self.eid,
            'fp': self.fp,
        }

    @deprecated
    def login_by_username(self):
        if self.is_login:
            logger.info('登录成功')
            return True

        username = input('账号:')
        password = input('密码:')
        if (not username) or (not password):
            logger.error('用户名或密码不能为空')
            return False
        self.username = username

        data = self._get_login_data()
        uuid = data['uuid']

        auth_code = ''
        if self._need_auth_code(username):
            logger.info('本次登录需要验证码')
            auth_code = self._get_auth_code(uuid)
        else:
            logger.info('本次登录不需要验证码')

        login_url = "https://passport.jd.com/uc/loginService"
        payload = {
            'uuid': uuid,
            'version': 2015,
            'r': random.random(),
        }
        data['authcode'] = auth_code
        data['loginname'] = username
        data['nloginpwd'] = encrypt_pwd(password)
        headers = {
            'User-Agent': self.user_agent,
            'Origin': 'https://passport.jd.com',
        }
        resp = self.sess.post(url=login_url, data=data, headers=headers, params=payload)

        if not response_status(resp):
            logger.error('登录失败')
            return False

        if not self._get_login_result(resp):
            return False

        # login success
        logger.info('登录成功')
        self.nick_name = self.get_user_info()
        self._save_cookies()
        self.is_login = True
        return True

    @deprecated
    def _get_login_result(self, resp):
        resp_json = parse_json(resp.text)
        error_msg = ''
        if 'success' in resp_json:
            # {"success":"http://www.jd.com"}
            return True
        elif 'emptyAuthcode' in resp_json:
            # {'_t': '_t', 'emptyAuthcode': '请输入验证码'}
            # {'_t': '_t', 'emptyAuthcode': '验证码不正确或验证码已过期'}
            error_msg = resp_json['emptyAuthcode']
        elif 'username' in resp_json:
            # {'_t': '_t', 'username': '账户名不存在，请重新输入'}
            # {'username': '服务器繁忙，请稍后再试', 'venture': 'xxxx', 'p': 'xxxx', 'ventureRet': 'http://www.jd.com/', '_t': '_t'}
            if resp_json['username'] == '服务器繁忙，请稍后再试':
                error_msg = resp_json['username'] + '(预计账户存在风险，需短信激活)'
            else:
                error_msg = resp_json['username']
        elif 'pwd' in resp_json:
            # {'pwd': '账户名与密码不匹配，请重新输入', '_t': '_t'}
            error_msg = resp_json['pwd']
        else:
            error_msg = resp_json
        logger.error(error_msg)
        return False

    def _get_QRcode(self):
        url = 'https://qr.m.jd.com/show'
        payload = {
            'appid': 133,
            'size': 147,
            't': str(int(time.time() * 1000)),
        }
        headers = {
            'User-Agent': self.user_agent,
            'Referer': 'https://passport.jd.com/',
        }
        resp = self.sess.get(url=url, headers=headers, params=payload)

        if not response_status(resp):
            logger.info('获取二维码失败')
            return False

        QRCode_file = '../QRcode.png'
        save_image(resp, QRCode_file)
        logger.info('二维码获取成功，请打开京东APP扫描')
        open_image(QRCode_file)
        return True

    def _get_QRcode_ticket(self):
        url = 'https://qr.m.jd.com/check'
        payload = {
            'appid': '133',
            'callback': 'jQuery{}'.format(random.randint(1000000, 9999999)),
            'token': self.sess.cookies.get('wlfstk_smdl'),
            '_': str(int(time.time() * 1000)),
        }
        headers = {
            'User-Agent': self.user_agent,
            'Referer': 'https://passport.jd.com/',
        }
        resp = self.sess.get(url=url, headers=headers, params=payload)

        if not response_status(resp):
            logger.error('获取二维码扫描结果异常')
            return False

        resp_json = parse_json(resp.text)
        if resp_json['code'] != 200:
            logger.info('Code: %s, Message: %s', resp_json['code'], resp_json['msg'])
            return None
        else:
            logger.info('已完成手机客户端确认')
            return resp_json['ticket']

    def _validate_QRcode_ticket(self, ticket):
        url = 'https://passport.jd.com/uc/qrCodeTicketValidation'
        headers = {
            'User-Agent': self.user_agent,
            'Referer': 'https://passport.jd.com/uc/login?ltype=logout',
        }
        resp = self.sess.get(url=url, headers=headers, params={'t': ticket})

        if not response_status(resp):
            return False

        resp_json = json.loads(resp.text)
        if resp_json['returnCode'] == 0:
            return True
        else:
            logger.info(resp_json)
            return False

    def login_by_QRcode(self):
        """二维码登陆
        :return:
        """
        br = self.init_browser()
        domain = '.jd.com'
        br.openUrl(f'https://www{domain}')
        br.set_cookies(self.sess.cookies, domain)

        if self.is_login:
            logger.info('登录成功')
        else:
            self._get_login_page()

            # download QR code
            if not self._get_QRcode():
                raise AsstException('二维码下载失败')

            # get QR code ticket
            ticket = None
            retry_times = 85
            for _ in range(retry_times):
                ticket = self._get_QRcode_ticket()
                if ticket:
                    break
                time.sleep(2)
            else:
                raise AsstException('二维码过期，请重新获取扫描')

            # validate QR code ticket
            if not self._validate_QRcode_ticket(ticket):
                raise AsstException('二维码信息校验失败')

            logger.info('二维码登录成功')
            self.is_login = True
            self.nick_name = self.get_user_info()
            self._save_cookies()

        # 获取下单必须参数
        self.init_order_request_info()

    def login_by_browser(self):
        """浏览器登录
        :return:
        """
        br = self.init_browser(False)
        br.client.set_window_size(375, 812)
        domain = '.m.jd.com'
        # br.openUrl(f'https://plogin{domain}/login/login')
        br.openUrl(f'https://plogin{domain}/login/login')
        # br.openUrl(f'https://passport{domain}/new/login.aspx')
        br.set_cookies(self.sess.cookies, domain)

        if self.is_login:
            # br.openUrl(f'https://m.jd.com/')
            logger.info('登录成功')
        else:
            retry_count = 60
            for _ in range(retry_count):
                pt_key = br.client.get_cookie('pt_key')
                if pt_key:
                    break
                time.sleep(2)
            else:
                br.quit()
                raise AsstException('登录时间过长，请重新启动')

            cookies = br.client.get_cookies()
            for cookie in cookies:
                if 'expiry' in cookie:
                    expires = cookie['expiry']
                else:
                    expires = None
                self.sess.cookies.set(cookie['name'], cookie['value']
                                      , domain=cookie['domain'], secure=cookie['secure'], expires=expires)

            if not self._validate_cookies():
                raise AsstException('浏览器登录校验失败')

            logger.info('浏览器登录成功')
            self.is_login = True
            self.nick_name = self.get_user_info()
            self._save_cookies()

        # 获取下单必须参数
        self.init_order_request_info()

    def _get_reserve_url(self, sku_id):
        url = 'https://yushou.jd.com/youshouinfo.action'
        payload = {
            'callback': 'fetchJSON',
            'sku': sku_id,
        }
        headers = {
            'User-Agent': self.user_agent,
            'Referer': 'https://item.jd.com/{}.html'.format(sku_id),
        }
        resp = self.sess.get(url=url, params=payload, headers=headers)
        resp_json = parse_json(resp.text)
        # {"type":"1","hasAddress":false,"riskCheck":"0","flag":false,"num":941723,"stime":"2018-10-12 12:40:00","plusEtime":"","qiangEtime":"","showPromoPrice":"0","qiangStime":"","state":2,"sku":100000287121,"info":"\u9884\u7ea6\u8fdb\u884c\u4e2d","isJ":0,"address":"","d":48824,"hidePrice":"0","yueEtime":"2018-10-19 15:01:00","plusStime":"","isBefore":0,"url":"//yushou.jd.com/toYuyue.action?sku=100000287121&key=237af0174f1cffffd227a2f98481a338","etime":"2018-10-19 15:01:00","plusD":48824,"category":"4","plusType":0,"yueStime":"2018-10-12 12:40:00"};
        reserve_url = resp_json.get('url')
        return 'https:' + reserve_url if reserve_url else None

    @check_login
    def make_reserve(self, sku_id):
        """商品预约
        :param sku_id: 商品id
        :return:
        """
        reserve_url = self._get_reserve_url(sku_id)
        if not reserve_url:
            logger.error('%s 非预约商品', sku_id)
            return
        headers = {
            'User-Agent': self.user_agent,
            'Referer': 'https://item.jd.com/{}.html'.format(sku_id),
        }
        resp = self.sess.get(url=reserve_url, headers=headers)
        soup = BeautifulSoup(resp.text, "html.parser")
        reserve_result = soup.find('p', {'class': 'bd-right-result'}).text.strip(' \t\r\n')
        # 预约成功，已获得抢购资格 / 您已成功预约过了，无需重复预约
        logger.info(reserve_result)

    @check_login
    def new_reserve(self, sku_id):
        """商品预约
        :param sku_id: 商品id
        :return:
        """
        try:
            page_url = 'https://wqs.jd.com/item/yuyue_item.shtml'
            page_payload = {
                'sceneval': '2',
                'buyNum': '2',
                'sku': sku_id,
                'isdraw': '',
                'activeid': '',
                'activetype': '',
                'ybServiceId': '',
                'homeServiceId': '',
                'ycServiceId': '',
                'jxsid': str(int(time.time() * 1000)) + str(random.random())[2:7]
            }
            page_headers = {
                'dnt': '1',
                'referer': 'https://item.m.jd.com/',
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'same-site',
                'sec-fetch-user': '?1',
                'upgrade-insecure-requests': '1',
                'User-Agent': self.user_agent
            }
            page_resp = self.sess.get(url=page_url, params=page_payload, headers=page_headers)
            page_html = page_resp.text

            if not page_html:
                logger.error('商品 %s 预约页面加载失败', sku_id)

            yuyue_url = 'https://wq.jd.com/bases/yuyue/item'
            yuyue_payload = {
                'callback': f'subscribeItemCB{self.letterMap[1]}',
                'dataType': '1',
                'skuId': sku_id,
                'sceneval': '2'
            }
            yuyue_headers = {
                'dnt': '1',
                'referer': 'https://wqs.jd.com/',
                'sec-fetch-dest': 'script',
                'sec-fetch-mode': 'no-cors',
                'sec-fetch-site': 'same-site',
                # 'sec-fetch-user': '?1',
                # 'upgrade-insecure-requests': '1',
                'User-Agent': self.user_agent
            }
            yuyue_resp = self.sess.get(url=yuyue_url, params=yuyue_payload, headers=yuyue_headers)
            yuyue_json = yuyue_resp.text
            if yuyue_json:
                if '"replyMsg":"预约成功"' in yuyue_json:
                    logger.info("商品 %s 预约成功", sku_id)
                    return True
                elif 'replyMsg: "您已经成功预约，不需重复预约"' in yuyue_json:
                    logger.info("商品 %s 已经预约", sku_id)
                    return True
            logger.error('响应数据：%s', yuyue_json)
        except Exception as e:
            logger.error(e)
        logger.error('商品 %s 预约失败，请手动预约', sku_id)
        return False

    @check_login
    def get_user_info(self):
        """获取用户信息
        :return: 用户名
        """
        if self.use_new:
            return self.nick_name
        else:
            url = 'https://passport.jd.com/user/petName/getUserInfoForMiniJd.action'
            payload = {
                'callback': 'jQuery{}'.format(random.randint(1000000, 9999999)),
                '_': str(int(time.time() * 1000)),
            }
            headers = {
                'User-Agent': self.user_agent,
                'Referer': 'https://order.jd.com/center/list.action',
            }
            try:
                resp = self.sess.get(url=url, params=payload, headers=headers)
                resp_json = parse_json(resp.text)
                # many user info are included in response, now return nick name in it
                # jQuery2381773({"imgUrl":"//storage.360buyimg.com/i.imageUpload/xxx.jpg","lastLoginTime":"","nickName":"xxx","plusStatus":"0","realName":"xxx","userLevel":x,"userScoreVO":{"accountScore":xx,"activityScore":xx,"consumptionScore":xxxxx,"default":false,"financeScore":xxx,"pin":"xxx","riskScore":x,"totalScore":xxxxx}})
                return resp_json.get('nickName') or 'jd'
            except Exception:
                return 'jd'

    def new_get_item_detail_page(self, sku_id):
        """访问商品详情页
        :param sku_id: 商品id
        :return: 响应
        """
        url = 'https://item.m.jd.com/product/{}.html'.format(sku_id)
        headers = self.headers.copy()
        headers['dnt'] = '1'
        headers['sec-fetch-user'] = '?1'
        headers['sec-fetch-site'] = 'none'
        headers['sec-fetch-mode'] = 'navigate'
        headers['sec-fetch-dest'] = 'document'
        headers['upgrade-insecure-requests'] = '1'
        page = self.sess.get(url=url, headers=headers)
        return page

    def _get_item_detail_page(self, sku_id):
        """访问商品详情页
        :param sku_id: 商品id
        :return: 响应
        """
        url = 'https://item.jd.com/{}.html'.format(sku_id)
        page = requests.get(url=url, headers=self.headers)
        return page

    def get_single_item_stock(self, sku_id, num, area):
        """获取单个商品库存状态
        :param sku_id: 商品id
        :param num: 商品数量
        :param area: 地区id
        :return: 商品是否有货 True/False
        """
        area_id = parse_area_id(area)

        cat = self.item_cat.get(sku_id)
        vender_id = self.item_vender_ids.get(sku_id)
        if not cat:
            page = self._get_item_detail_page(sku_id)
            match = re.search(r'cat: \[(.*?)\]', page.text)
            cat = match.group(1)
            self.item_cat[sku_id] = cat

            match = re.search(r'venderId:(\d*?),', page.text)
            vender_id = match.group(1)
            self.item_vender_ids[sku_id] = vender_id

        url = 'https://c0.3.cn/stock'
        payload = {
            'skuId': sku_id,
            'buyNum': num,
            'area': area_id,
            'ch': 1,
            '_': str(int(time.time() * 1000)),
            'callback': 'jQuery{}'.format(random.randint(1000000, 9999999)),
            'extraParam': '{"originid":"1"}',  # get error stock state without this param
            'cat': cat,  # get 403 Forbidden without this param (obtained from the detail page)
            'venderId': vender_id  # return seller information with this param (can't be ignored)
        }
        headers = {
            'User-Agent': self.user_agent,
            'Referer': 'https://item.jd.com/{}.html'.format(sku_id),
        }

        resp_text = ''
        try:
            resp_text = requests.get(url=url, params=payload, headers=headers, timeout=self.timeout).text
            resp_json = parse_json(resp_text)
            stock_info = resp_json.get('stock')
            sku_state = stock_info.get('skuState')  # 商品是否上架
            stock_state = stock_info.get('StockState')  # 商品库存状态：33 -- 现货  0,34 -- 无货  36 -- 采购中  40 -- 可配货
            return sku_state == 1 and stock_state in (33, 40)
        except requests.exceptions.Timeout:
            logger.error('查询 %s 库存信息超时(%ss)', sku_id, self.timeout)
            return False
        except requests.exceptions.RequestException as request_exception:
            logger.error('查询 %s 库存信息发生网络请求异常：%s', sku_id, request_exception)
            return False
        except Exception as e:
            logger.error('查询 %s 库存信息发生异常, resp: %s, exception: %s', sku_id, resp_text, e)
            return False

    @check_login
    def get_multi_item_stock(self, sku_ids, area):
        """获取多个商品库存状态（旧）

        该方法需要登陆才能调用，用于同时查询多个商品的库存。
        京东查询接口返回每种商品的状态：有货/无货。当所有商品都有货，返回True；否则，返回False。

        :param sku_ids: 多个商品的id。可以传入中间用英文逗号的分割字符串，如"123,456"
        :param area: 地区id
        :return: 多个商品是否同时有货 True/False
        """
        items_dict = parse_sku_id(sku_ids=sku_ids)
        area_id_list = split_area_id(area)

        url = 'https://trade.jd.com/api/v1/batch/stock'
        headers = {
            'User-Agent': self.user_agent,
            'Origin': 'https://trade.jd.com',
            'Content-Type': 'application/json; charset=UTF-8',
            'Referer': 'https://trade.jd.com/shopping/order/getOrderInfo.action?rid=' + str(int(time.time() * 1000)),
        }
        data = {
            "areaRequest": {
                "provinceId": area_id_list[0],
                "cityId": area_id_list[1],
                "countyId": area_id_list[2],
                "townId": area_id_list[3]
            },
            "skuNumList": []
        }
        for sku_id, count in items_dict.items():
            data['skuNumList'].append({
                "skuId": sku_id,
                "num": count
            })
        # convert to string
        data = json.dumps(data)

        try:
            resp = self.sess.post(url=url, headers=headers, data=data, timeout=self.timeout)
        except requests.exceptions.Timeout:
            logger.error('查询 %s 库存信息超时(%ss)', list(items_dict.keys()), self.timeout)
            return False
        except requests.exceptions.RequestException as e:
            raise AsstException('查询 %s 库存信息异常：%s' % (list(items_dict.keys()), e))

        resp_json = parse_json(resp.text)
        result = resp_json.get('result')

        stock = True
        for sku_id in result:
            status = result.get(sku_id).get('status')
            if '无货' in status:
                stock = False
                break

        return stock

    def get_multi_item_stock_new(self, sku_ids, area):
        """获取多个商品库存状态（新）

        当所有商品都有货，返回True；否则，返回False。

        :param sku_ids: 多个商品的id。可以传入中间用英文逗号的分割字符串，如"123,456"
        :param area: 地区id
        :return: 多个商品是否同时有货 True/False
        """
        items_dict = parse_sku_id(sku_ids=sku_ids)
        area_id = parse_area_id(area=area)

        url = 'https://c0.3.cn/stocks'
        payload = {
            'callback': 'jQuery{}'.format(random.randint(1000000, 9999999)),
            'type': 'getstocks',
            'skuIds': ','.join(items_dict.keys()),
            'area': area_id,
            '_': str(int(time.time() * 1000))
        }
        headers = {
            'User-Agent': self.user_agent
        }

        resp_text = ''
        try:
            resp_text = requests.get(url=url, params=payload, headers=headers, timeout=self.timeout).text
            stock = True
            for sku_id, info in parse_json(resp_text).items():
                sku_state = info.get('skuState')  # 商品是否上架
                stock_state = info.get('StockState')  # 商品库存状态
                if sku_state == 1 and stock_state in (33, 40):
                    continue
                else:
                    stock = False
                    break
            return stock
        except requests.exceptions.Timeout:
            logger.error('查询 %s 库存信息超时(%ss)', list(items_dict.keys()), self.timeout)
            return False
        except requests.exceptions.RequestException as request_exception:
            logger.error('查询 %s 库存信息发生网络请求异常：%s', list(items_dict.keys()), request_exception)
            return False
        except Exception as e:
            logger.error('查询 %s 库存信息发生异常, resp: %s, exception: %s', list(items_dict.keys()), resp_text, e)
            return False

    def _if_item_removed(self, sku_id):
        """判断商品是否下架
        :param sku_id: 商品id
        :return: 商品是否下架 True/False
        """
        detail_page = self._get_item_detail_page(sku_id=sku_id)
        return '该商品已下柜' in detail_page.text

    @check_login
    def if_item_can_be_ordered(self, sku_ids, area):
        """判断商品是否能下单
        :param sku_ids: 商品id，多个商品id中间使用英文逗号进行分割
        :param area: 地址id
        :return: 商品是否能下单 True/False
        """
        items_dict = parse_sku_id(sku_ids=sku_ids)
        area_id = parse_area_id(area)

        # 判断商品是否能下单
        if len(items_dict) > 1:
            return self.get_multi_item_stock_new(sku_ids=items_dict, area=area_id)

        sku_id, count = list(items_dict.items())[0]
        return self.get_single_item_stock(sku_id=sku_id, num=count, area=area_id)

    def get_item_price(self, sku_id):
        """获取商品价格
        :param sku_id: 商品id
        :return: 价格
        """
        url = 'http://p.3.cn/prices/mgets'
        payload = {
            'type': 1,
            'pduid': int(time.time() * 1000),
            'skuIds': 'J_' + sku_id,
        }
        resp = self.sess.get(url=url, params=payload)
        return parse_json(resp.text).get('p')

    @check_login
    def add_item_to_cart(self, sku_ids):
        """添加商品到购物车

        重要：
        1.商品添加到购物车后将会自动被勾选✓中。
        2.在提交订单时会对勾选的商品进行结算。
        3.部分商品（如预售、下架等）无法添加到购物车

        京东购物车可容纳的最大商品种数约为118-120种，超过数量会加入购物车失败。

        :param sku_ids: 商品id，格式："123" 或 "123,456" 或 "123:1,456:2"。若不配置数量，默认为1个。
        :return:
        """

        add_cart_request = self.request_info['add_cart_request']

        for sku_id, count in parse_sku_id(sku_ids=sku_ids).items():
            payload = {
                'pid': sku_id,
                'pcount': count,
                'ptype': 1,
            }
            add_cart_request(payload)

    @check_login
    def clear_cart(self):
        """清空购物车

        包括两个请求：
        1.选中购物车中所有的商品
        2.批量删除

        :return: 清空购物车结果 True/False
        """
        # 1.select all items  2.batch remove items
        select_url = 'https://cart.jd.com/selectAllItem.action'
        remove_url = 'https://cart.jd.com/batchRemoveSkusFromCart.action'
        data = {
            't': 0,
            'outSkus': '',
            'random': random.random(),
        }
        try:
            select_resp = self.sess.post(url=select_url, data=data)
            time.sleep(2)
            remove_resp = self.sess.post(url=remove_url, data=data)
            if (not response_status(select_resp)) or (not response_status(remove_resp)):
                logger.error('购物车清空失败')
                return False
            logger.info('购物车清空成功')
            return True
        except Exception as e:
            logger.error(e)
            return False

    @check_login
    def get_cart_detail(self):
        """获取购物车商品详情
        :return: 购物车商品信息 dict
        """
        url = 'https://cart.jd.com/cart.action'
        resp = self.sess.get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        cart_detail = dict()
        for item in soup.find_all(class_='item-item'):
            try:
                sku_id = item['skuid']  # 商品id
                # 例如：['increment', '8888', '100001071956', '1', '13', '0', '50067652554']
                # ['increment', '8888', '100002404322', '2', '1', '0']
                item_attr_list = item.find(class_='increment')['id'].split('_')
                p_type = item_attr_list[4]
                promo_id = target_id = item_attr_list[-1] if len(item_attr_list) == 7 else 0

                cart_detail[sku_id] = {
                    'name': get_tag_value(item.select('div.p-name a')),  # 商品名称
                    'verder_id': item['venderid'],  # 商家id
                    'count': int(item['num']),  # 数量
                    'unit_price': get_tag_value(item.select('div.p-price strong'))[1:],  # 单价
                    'total_price': get_tag_value(item.select('div.p-sum strong'))[1:],  # 总价
                    'is_selected': 'item-selected' in item['class'],  # 商品是否被勾选
                    'p_type': p_type,
                    'target_id': target_id,
                    'promo_id': promo_id
                }
            except Exception as e:
                logger.error("某商品在购物车中的信息无法解析，报错信息: %s，该商品自动忽略。 %s", e, item)

        logger.info('购物车信息：%s', cart_detail)
        return cart_detail

    def _cancel_select_all_cart_item(self):
        """取消勾选购物车中的所有商品
        :return: 取消勾选结果 True/False
        """
        url = "https://cart.jd.com/cancelAllItem.action"
        data = {
            't': 0,
            'outSkus': '',
            'random': random.random()
            # 'locationId' can be ignored
        }
        resp = self.sess.post(url, data=data)
        return response_status(resp)

    def _change_item_num_in_cart(self, sku_id, vender_id, num, p_type, target_id, promo_id):
        """修改购物车商品的数量
        修改购物车中商品数量后，该商品将会被自动勾选上。

        :param sku_id: 商品id
        :param vender_id: 商家id
        :param num: 目标数量
        :param p_type: 商品类型(可能)
        :param target_id: 参数用途未知，可能是用户判断优惠
        :param promo_id: 参数用途未知，可能是用户判断优惠
        :return: 商品数量修改结果 True/False
        """
        url = "https://cart.jd.com/changeNum.action"
        data = {
            't': 0,
            'venderId': vender_id,
            'pid': sku_id,
            'pcount': num,
            'ptype': p_type,
            'targetId': target_id,
            'promoID': promo_id,
            'outSkus': '',
            'random': random.random(),
            # 'locationId'
        }
        headers = {
            'User-Agent': self.user_agent,
            'Referer': 'https://cart.jd.com/cart',
        }
        resp = self.sess.post(url, data=data, headers=headers)
        return json.loads(resp.text)['sortedWebCartResult']['achieveSevenState'] == 2

    def _add_or_change_cart_item(self, cart, sku_id, count):
        """添加商品到购物车，或修改购物车中商品数量

        如果购物车中存在该商品，会修改该商品的数量并勾选；否则，会添加该商品到购物车中并勾选。

        :param cart: 购物车信息 dict
        :param sku_id: 商品id
        :param count: 商品数量
        :return: 运行结果 True/False
        """
        if sku_id in cart:
            logger.info('%s 已在购物车中，调整数量为 %s', sku_id, count)
            cart_item = cart.get(sku_id)
            return self._change_item_num_in_cart(
                sku_id=sku_id,
                vender_id=cart_item.get('vender_id'),
                num=count,
                p_type=cart_item.get('p_type'),
                target_id=cart_item.get('target_id'),
                promo_id=cart_item.get('promo_id')
            )
        else:
            logger.info('%s 不在购物车中，开始加入购物车，数量 %s', sku_id, count)
            return self.add_item_to_cart(sku_ids={sku_id: count})

    @check_login
    def get_checkout_page_detail(self):
        """获取订单结算页面信息

        该方法会返回订单结算页面的详细信息：商品名称、价格、数量、库存状态等。

        :return: 结算信息 dict
        """

        get_checkout_page_request = self.request_info['get_checkout_page_request']

        payload = {
            'rid': str(int(time.time() * 1000)),
        }

        get_checkout_page_request(payload)

    def _save_invoice(self):
        """下单第三方商品时如果未设置发票，将从电子发票切换为普通发票

        http://jos.jd.com/api/complexTemplate.htm?webPamer=invoice&groupName=%E5%BC%80%E6%99%AE%E5%8B%92%E5%85%A5%E9%A9%BB%E6%A8%A1%E5%BC%8FAPI&id=566&restName=jd.kepler.trade.submit&isMulti=true

        :return:
        """
        url = 'https://trade.jd.com/shopping/dynamic/invoice/saveInvoice.action'
        data = {
            "invoiceParam.selectedInvoiceType": 1,
            "invoiceParam.companyName": "个人",
            "invoiceParam.invoicePutType": 0,
            "invoiceParam.selectInvoiceTitle": 4,
            "invoiceParam.selectBookInvoiceContent": "",
            "invoiceParam.selectNormalInvoiceContent": 1,
            "invoiceParam.vatCompanyName": "",
            "invoiceParam.code": "",
            "invoiceParam.regAddr": "",
            "invoiceParam.regPhone": "",
            "invoiceParam.regBank": "",
            "invoiceParam.regBankAccount": "",
            "invoiceParam.hasCommon": "true",
            "invoiceParam.hasBook": "false",
            "invoiceParam.consigneeName": "",
            "invoiceParam.consigneePhone": "",
            "invoiceParam.consigneeAddress": "",
            "invoiceParam.consigneeProvince": "请选择：",
            "invoiceParam.consigneeProvinceId": "NaN",
            "invoiceParam.consigneeCity": "请选择",
            "invoiceParam.consigneeCityId": "NaN",
            "invoiceParam.consigneeCounty": "请选择",
            "invoiceParam.consigneeCountyId": "NaN",
            "invoiceParam.consigneeTown": "请选择",
            "invoiceParam.consigneeTownId": 0,
            "invoiceParam.sendSeparate": "false",
            "invoiceParam.usualInvoiceId": "",
            "invoiceParam.selectElectroTitle": 4,
            "invoiceParam.electroCompanyName": "undefined",
            "invoiceParam.electroInvoiceEmail": "",
            "invoiceParam.electroInvoicePhone": "",
            "invokeInvoiceBasicService": "true",
            "invoice_ceshi1": "",
            "invoiceParam.showInvoiceSeparate": "false",
            "invoiceParam.invoiceSeparateSwitch": 1,
            "invoiceParam.invoiceCode": "",
            "invoiceParam.saveInvoiceFlag": 1
        }
        headers = {
            'User-Agent': self.user_agent,
            'Referer': 'https://trade.jd.com/shopping/dynamic/invoice/saveInvoice.action',
        }
        self.sess.post(url=url, data=data, headers=headers)

    @check_login
    def submit_order(self):
        """提交订单

        重要：
        1.该方法只适用于普通商品的提交订单（即可以加入购物车，然后结算提交订单的商品）
        2.提交订单时，会对购物车中勾选✓的商品进行结算（如果勾选了多个商品，将会提交成一个订单）

        :return: True/False 订单提交结果
        """
        submit_order_request = self.request_info['submit_order_request']

        return submit_order_request()

    @check_login
    def submit_order_with_retry(self, retry=3, interval=4):
        """提交订单，并且带有重试功能
        :param retry: 重试次数
        :param interval: 重试间隔
        :return: 订单提交结果 True/False
        """
        for i in range(1, retry + 1):
            logger.info('第[%s/%s]次尝试提交订单', i, retry)
            self.get_checkout_page_detail()
            if self.submit_order():
                logger.info('第%s次提交订单成功', i)
                return True
            else:
                if i < retry:
                    logger.info('第%s次提交失败，%ss后重试', i, interval)
                    time.sleep(interval)
        else:
            logger.info('重试提交%s次结束', retry)
            return False

    @check_login
    def submit_order_by_time(self, buy_time, retry=4, interval=5):
        """定时提交商品订单

        重要：该方法只适用于普通商品的提交订单，事先需要先将商品加入购物车并勾选✓。

        :param buy_time: 下单时间，例如：'2018-09-28 22:45:50.000'
        :param retry: 下单重复执行次数，可选参数，默认4次
        :param interval: 下单执行间隔，可选参数，默认5秒
        :return:
        """
        t = Timer(buy_time=buy_time)
        t.start()

        for count in range(1, retry + 1):
            logger.info('第[%s/%s]次尝试提交订单', count, retry)
            if self.submit_order():
                break
            logger.info('休息%ss', interval)
            time.sleep(interval)
        else:
            logger.info('执行结束，提交订单失败！')

    @check_login
    def get_order_info(self, unpaid=True):
        """查询订单信息
        :param unpaid: 只显示未付款订单，可选参数，默认为True
        :return:
        """
        url = 'https://order.jd.com/center/list.action'
        payload = {
            'search': 0,
            'd': 1,
            's': 4096,
        }  # Orders for nearly three months
        headers = {
            'User-Agent': self.user_agent,
            'Referer': 'https://passport.jd.com/uc/login?ltype=logout',
        }

        try:
            resp = self.sess.get(url=url, params=payload, headers=headers)
            if not response_status(resp):
                logger.error('获取订单页信息失败')
                return
            soup = BeautifulSoup(resp.text, "html.parser")

            logger.info('************************订单列表页查询************************')
            order_table = soup.find('table', {'class': 'order-tb'})
            table_bodies = order_table.select('tbody')
            exist_order = False
            for table_body in table_bodies:
                # get order status
                order_status = get_tag_value(table_body.select('span.order-status')).replace("订单状态：", "")

                # check if order is waiting for payment
                # wait_payment = bool(table_body.select('a.btn-pay'))
                wait_payment = "等待付款" in order_status

                # only show unpaid orders if unpaid=True
                if unpaid and (not wait_payment):
                    continue

                exist_order = True

                # get order_time, order_id
                tr_th = table_body.select('tr.tr-th')[0]
                order_time = get_tag_value(tr_th.select('span.dealtime'))
                order_id = get_tag_value(tr_th.select('span.number a'))

                # get sum_price, pay_method
                sum_price = ''
                pay_method = ''
                amount_div = table_body.find('div', {'class': 'amount'})
                if amount_div:
                    spans = amount_div.select('span')
                    pay_method = get_tag_value(spans, index=1)
                    # if the order is waiting for payment, the price after the discount is shown.
                    sum_price = get_tag_value(amount_div.select('strong'), index=1)[1:] if wait_payment \
                        else get_tag_value(spans, index=0)[4:]

                # get name and quantity of items in order
                items_dict = dict()  # {'item_id_1': quantity_1, 'item_id_2': quantity_2, ...}
                tr_bds = table_body.select('tr.tr-bd')
                for tr_bd in tr_bds:
                    item = tr_bd.find('div', {'class': 'goods-item'})
                    if not item:
                        break
                    item_id = item.get('class')[1][2:]
                    quantity = get_tag_value(tr_bd.select('div.goods-number'))[1:]
                    items_dict[item_id] = quantity

                order_info_format = '下单时间:{0}----订单号:{1}----商品列表:{2}----订单状态:{3}----总金额:{4}元----付款方式:{5}'
                logger.info(order_info_format.format(order_time, order_id, parse_items_dict(items_dict), order_status,
                                                     sum_price, pay_method))

            if not exist_order:
                logger.info('订单查询为空')
        except Exception as e:
            logger.error(e)

    @deprecated
    def _get_seckill_url(self, sku_id, server_buy_time=int(time.time())):
        """获取商品的抢购链接

        点击"抢购"按钮后，会有两次302跳转，最后到达订单结算页面
        这里返回第一次跳转后的页面url，作为商品的抢购链接

        :param sku_id: 商品id
        :return: 商品的抢购链接
        """
        url = 'https://itemko.jd.com/itemShowBtn'
        payload = {
            'callback': 'jQuery{}'.format(random.randint(1000000, 9999999)),
            'skuId': sku_id,
            'from': 'pc',
            '_': str(server_buy_time * 1000),
        }
        headers = {
            'User-Agent': self.user_agent,
            'Host': 'itemko.jd.com',
            'Referer': 'https://item.jd.com/{}.html'.format(sku_id),
        }
        retry_interval = global_config.retry_interval
        retry_count = 0

        while retry_count < 10:
            resp = self.sess.get(url=url, headers=headers, params=payload, timeout=(0.1, 0.08))
            resp_json = parse_json(resp.text)
            if resp_json.get('url'):
                # https://divide.jd.com/user_routing?skuId=8654289&sn=c3f4ececd8461f0e4d7267e96a91e0e0&from=pc
                router_url = 'https:' + resp_json.get('url')
                # https://marathon.jd.com/captcha.html?skuId=8654289&sn=c3f4ececd8461f0e4d7267e96a91e0e0&from=pc
                seckill_url = router_url.replace('divide', 'marathon').replace('user_routing', 'captcha.html')
                logger.info("抢购链接获取成功: %s", seckill_url)
                return seckill_url
            else:
                retry_count += 1
                logger.info("第%s次获取抢购链接失败，%s不是抢购商品或抢购页面暂未刷新，%s秒后重试", retry_count, sku_id, retry_interval)
                time.sleep(retry_interval)

        logger.error("抢购链接获取失败，终止抢购！")
        exit(-1)

    def request_seckill_url(self, sku_id, server_buy_time):
        """访问商品的抢购链接（用于设置cookie等）
        :param sku_id: 商品id
        :return:
        """
        if not self.seckill_url.get(sku_id):
            seckill_url = self.request_info['get_sku_seckill_url_request'](sku_id, server_buy_time)
            if seckill_url is not None:
                self.seckill_url[sku_id] = seckill_url
            else:
                return None
        return self.request_info['request_sku_seckill_url_request'](sku_id)

    @deprecated
    def request_seckill_checkout_page(self, sku_id, num=1):
        """访问抢购订单结算页面
        :param sku_id: 商品id
        :param num: 购买数量，可选参数，默认1个
        :return:
        """
        url = 'https://marathon.jd.com/seckill/seckill.action'
        payload = {
            'skuId': sku_id,
            'num': num,
            'rid': int(time.time())
        }
        headers = {
            'User-Agent': self.user_agent,
            'Host': 'marathon.jd.com',
            'Referer': 'https://item.jd.com/{}.html'.format(sku_id),
        }
        self.sess.get(url=url, params=payload, headers=headers, timeout=(0.1, 0.08))

    def _get_seckill_init_info(self, sku_id, num=1):
        """获取秒杀初始化信息（包括：地址，发票，token）
        :param sku_id:
        :param num: 购买数量，可选参数，默认1个
        :return: 初始化信息组成的dict
        """
        count = 1
        while count < 8:
            logger.info('第 %s 次获取秒杀初始化信息', count)
            content = self.request_info['get_seckill_init_info_request'](sku_id, num)
            try:
                if 'koFail' in content:
                    logger.error('抢购失败，请求重定向，地址：%s', content)
                else:
                    return parse_json(content)
            except Exception as e:
                logger.error('获取秒杀初始化信息失败，响应数据：%s，异常：%s', content, e)
            count += 1

    def _gen_seckill_order_data(self, sku_id, num=1):
        """生成提交抢购订单所需的请求体参数
        :param sku_id: 商品id
        :param num: 购买数量，可选参数，默认1个
        :return: 请求体参数组成的dict
        """

        # 获取用户秒杀初始化信息
        init_info = self.seckill_init_info.get(sku_id)
        if not init_info:
            init_info = self._get_seckill_init_info(sku_id)
            self.seckill_init_info[sku_id] = init_info

        default_address = init_info['addressList'][0]  # 默认地址dict
        invoice_info = init_info.get('invoiceInfo', {})  # 默认发票信息dict, 有可能不返回
        token = init_info['token']

        data = {
            'skuId': sku_id,
            'num': num,
            'addressId': default_address['id'],
            'yuShou': str(bool(int(init_info['seckillSkuVO']['extMap'].get('YuShou', '0')))).lower(),
            'isModifyAddress': 'false',
            'name': default_address['name'],
            'provinceId': default_address['provinceId'],
            'cityId': default_address['cityId'],
            'countyId': default_address['countyId'],
            'townId': default_address['townId'],
            'addressDetail': default_address['addressDetail'],
            'mobile': default_address['mobile'],
            'mobileKey': default_address['mobileKey'],
            'email': default_address.get('email', ''),
            'postCode': '',
            'invoiceTitle': invoice_info.get('invoiceTitle', -1),
            'invoiceCompanyName': '',
            'invoiceContent': invoice_info.get('invoiceContentType', 1),
            'invoiceTaxpayerNO': '',
            'invoiceEmail': '',
            'invoicePhone': invoice_info.get('invoicePhone', ''),
            'invoicePhoneKey': invoice_info.get('invoicePhoneKey', ''),
            'invoice': 'true' if invoice_info else 'false',
            'password': global_config.get('account', 'payment_pwd'),
            'codTimeType': 3,
            'paymentType': 4,
            'areaCode': '',
            'overseas': 0,
            'phone': '',
            'eid': self.eid,
            'fp': self.fp,
            'token': token,
            'pru': ''
        }
        return data

    def exec_seckill(self, sku_id, server_buy_time=int(time.time()), retry=4, interval=4, num=1, fast_mode=True):
        """立即抢购

        抢购商品的下单流程与普通商品不同，不支持加入购物车，可能需要提前预约，主要执行流程如下：
        1. 访问商品的抢购链接
        2. 访问抢购订单结算页面（好像可以省略这步，待测试）
        3. 提交抢购（秒杀）订单

        :param sku_id: 商品id
        :param server_buy_time: 商品指定抢购时间
        :param retry: 抢购重复执行次数，可选参数，默认4次
        :param interval: 抢购执行间隔，可选参数，默认4秒
        :param num: 购买数量，可选参数，默认1个
        :param fast_mode: 快速模式：略过访问抢购订单结算页面这一步骤，默认为 True
        :return: 抢购结果 True/False
        """

        for count in range(1, retry + 1):
            logger.info('第[%s/%s]次尝试抢购商品:%s', count, retry, sku_id)

            if not fast_mode:
                # 访问抢购订单结算页面
                self.request_info['request_seckill_checkout_page_request'](sku_id, num)

            if self.request_info['submit_seckill_order_request'](sku_id, server_buy_time, num):
                return True
            else:
                logger.info('休息%ss', interval)
                time.sleep(interval)
        else:
            logger.info('执行结束，抢购%s失败！', sku_id)
            return False

    @check_login
    def exec_seckill_by_time(self, config):
        """预约抢购
        """

        if not config:
            raise AsstException('初始化配置为空！')

        self.config = config

        # 兼容正常流程：开抢前清空购物车
        self.clear_cart()

        items_dict = parse_sku_id(sku_ids=config.sku_id)

        if self.use_new:
            server_buy_time, realy_buy_time = self.new_init_seckill_request_method(config.fast_mode,
                                                                                   config.is_risk_control)
        else:
            # 1.提前初始化预约抢购流程请求信息、方法
            server_buy_time, realy_buy_time = self.init_seckill_request_method(config.fast_mode, config.is_risk_control)
            # 兼容正常流程：初始化正常下单流程请求信息、方法
            self.init_default_order_request_method(config.fast_mode, config.is_risk_control)

        Timer.setSystemTime()

        # 使用多线程需要从倒计时前开始，后续流程都使用多线程执行

        if self.use_new:
            get_confirm_order_page_request = self.request_info['get_confirm_order_page_request']
            submit_order_request = self.request_info['submit_order_request']

            def start_func():

                # 订单请求页面
                for sku_id in items_dict:
                    logger.info('开始抢购商品:%s', sku_id)
                    submit_data = get_confirm_order_page_request(sku_id, server_buy_time)
                    if submit_data is not None:
                        retry = config.retry
                        interval = config.interval
                        for count in range(1, retry + 1):
                            logger.info('第[%s/%s]次尝试提交订单', count, retry)
                            with self.sem:
                                # 下单请求
                                if submit_order_request(submit_data, count):
                                    break
                                logger.info('休息%ss', interval)
                                time.sleep(interval)
                        else:
                            logger.info('执行结束，提交订单失败！')
                        continue
                    else:
                        return None
        else:
            def start_func():

                # 使用协程/多线程从执行开始
                # 3.执行
                for sku_id in items_dict:
                    logger.info('开始抢购商品:%s', sku_id)

                    # 获取抢购链接
                    resp = self.request_seckill_url(sku_id, server_buy_time)
                    if resp is not None:
                        if resp == 'pass':
                            pass
                        elif resp.status == 302:
                            location = resp.headers['location']
                            logger.info('访问商品抢购链接请求，重定向地址：%s', location)
                            if 'gate.action' in location:
                                # 此处转入正常购物车下单流程
                                add_cart_request = self.request_info['add_cart_request']
                                payload = {
                                    'pid': sku_id,
                                    'pcount': config.num,
                                    'ptype': 1,
                                }
                                add_cart_request(payload)
                                # 获取订单结算页面信息
                                self.get_checkout_page_detail()
                                retry = config.retry
                                interval = config.interval
                                for count in range(1, retry + 1):
                                    logger.info('第[%s/%s]次尝试提交订单', count, retry)
                                    with self.sem:
                                        if self.submit_order():
                                            break
                                        logger.info('休息%ss', interval)
                                        time.sleep(interval)
                                else:
                                    logger.info('执行结束，提交订单失败！')
                                continue

                    # 开始抢购
                    self.exec_seckill(sku_id, server_buy_time, config.retry, config.interval, int(items_dict[sku_id]),
                                      config.fast_mode)

        self.start_func = start_func

        # 2.倒计时
        logger.info('准备抢购商品:%s', list(items_dict.keys()))

        Timer(buy_time=realy_buy_time, sleep_interval=config.sleep_interval,
              fast_sleep_interval=config.fast_sleep_interval, is_sync=False, assistant=self).start()

        if self.config.fast_mode:
            self.close_now()

    def new_parse_item_detail_page(self, sku_id, html):
        match = re.search(r'"zzz":\"(.*)\"', html)
        if not match:
            return False
        zzz = match.group(1)
        if zzz is None:
            return False

        self.item_zzz[sku_id] = zzz

        area_id_list = list(map(lambda x: x.strip(), re.split('_|-', self.area_id)))

        area_url = ''
        if len(area_id_list) > 2:
            area_url = area_id_list[0] + '-' + area_id_list[1] + '-' + area_id_list[2]

        item_url_param = 'sceneval=2&bid=&scene=jd&isCanEdit=1&EncryptInfo=&Token=&type=0&lg=0&supm=0&locationid=' + area_url + '&favorablerate=94'

        self.item_url_param[sku_id] = item_url_param

        return True

    def parse_item_detail_page(self, sku_id, page):
        match = re.search(r'cat: \[(.*?)\]', page.text)
        cat = match.group(1)
        if not cat:
            return False

        self.item_cat[sku_id] = cat

        match = re.search(r'venderId:(\d*?),', page.text)
        vender_id = match.group(1)
        self.item_vender_ids[sku_id] = vender_id

        match = re.search(r'paramJson:( ?)\'(\{.*\})\'', page.text)
        param_json = match.group(1)
        if not param_json or param_json == '' or param_json == ' ':
            param_json = match.group(2)
        if not param_json:
            param_json = ''
        self.param_json[sku_id] = param_json

        match = re.search(r'specialAttrs:( ?)(\[.*\])', page.text)
        special_attrs_str = match.group(1)
        if not special_attrs_str or special_attrs_str == '' or special_attrs_str == ' ':
            special_attrs_str = match.group(2)
        if special_attrs_str:
            special_attrs = json.loads(special_attrs_str)
        else:
            special_attrs = []
        self.special_attrs[sku_id] = special_attrs

        return True

    def new_init_yuyue_buy_time(self, sku_id=None, html=None):
        config = self.config

        logger.info('初始化预约抢购时间')
        # 处理时间
        server_buy_datetime = None
        if config.sku_buy_time:
            # 根据配置初始化
            server_buy_datetime = datetime.strptime(config.sku_buy_time, "%Y-%m-%d %H:%M:%S.%f")
        else:
            # 自动获取
            match = re.search(r'"yuyue":({.*})', html)
            if match:
                yuyue = match.group(1)
                if yuyue:
                    yuyue_json = parse_json(yuyue)
                    buy_start_time = yuyue_json['qiangStime']
                    if buy_start_time:
                        buy_end_time = yuyue_json['qiangEtime']
                        server_buy_datetime = datetime.strptime(buy_start_time, "%Y-%m-%d %H:%M:%S")
                        logger.info('商品%s预约抢购，开始时间:%s，结束时间:%s', sku_id, buy_start_time, buy_end_time)
                    else:
                        logger.debug(f"响应数据：{html}")
                        logger.info("商品%s无法获取预约抢购时间，请重新设置sku_id", sku_id)
                        exit(-1)
            else:
                logger.info("商品%s不是 预约抢购商品 或 未开始预约，请重新设置sku_id", sku_id)
                exit(-1)
        return int(time.mktime(server_buy_datetime.timetuple())), (
                server_buy_datetime + timedelta(milliseconds=-config.buy_time_offset)).strftime(
            "%Y-%m-%d %H:%M:%S.%f")

    def init_yuyue_buy_time(self, sku_id=None, header=None, payload=None):
        if header is None:
            header = dict()
        config = self.config

        logger.info('初始化预约抢购时间')
        # 处理时间
        server_buy_datetime = None
        if config.sku_buy_time:
            # 根据配置初始化
            server_buy_datetime = datetime.strptime(config.sku_buy_time, "%Y-%m-%d %H:%M:%S.%f")
        else:
            # 自动初始化
            header['Host'] = 'itemko.jd.com'
            header['Referer'] = 'https://item.jd.com/'
            resp = http_util.send_http_request(self.socket_client,
                                               url='https://item-soa.jd.com/getWareBusiness',
                                               method='GET',
                                               headers=header,
                                               params=payload,
                                               cookies=self.get_cookies_str_by_domain_or_path(
                                                   'item-soa.jd.com'))
            resp_data = resp.body
            resp_json = parse_json(resp_data)
            yuyue_info = resp_json.get('yuyueInfo')
            if yuyue_info:
                buy_time = yuyue_info.get('buyTime')
                if buy_time:
                    buy_time_list = re.findall(r'\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{1,2}', buy_time.strip())
                    if buy_time_list and len(buy_time_list) == 2:
                        buy_start_time = buy_time_list[0]
                        buy_end_time = buy_time_list[1]
                        server_buy_datetime = datetime.strptime(buy_start_time, "%Y-%m-%d %H:%M")
                        logger.info('商品%s预约抢购，开始时间:%s，结束时间:%s', sku_id, buy_start_time, buy_end_time)
                    else:
                        if resp_data:
                            logger.info(f"响应数据：{resp_data}")
                        logger.info("商品%s无法获取预约抢购时间，请重新设置sku_id", sku_id)
                        exit(-1)
                else:
                    if resp_data:
                        logger.info(f"响应数据：{resp_data}")
                    logger.info("商品%s无法获取预约抢购时间，请重新设置sku_id", sku_id)
                    exit(-1)
            else:
                logger.info("商品%s不是 预约抢购商品 或 未开始预约，请重新设置sku_id", sku_id)
                exit(-1)
        return int(time.mktime(server_buy_datetime.timetuple())), (
                server_buy_datetime + timedelta(milliseconds=-config.buy_time_offset)).strftime(
            "%Y-%m-%d %H:%M:%S.%f")

    def init_seckill_request_method(self, fast_mode, is_risk_control):
        # 提前初始化请求信息、方法
        # self.get_and_update_cookies_str()
        config = self.config
        sku_id = config.sku_id

        area_id = parse_area_id(self.area_id)
        cat = self.item_cat.get(sku_id)
        retry_count = 0
        while not cat:
            retry_count += 1
            logger.info('第 %s 次获取商品页信息', retry_count)
            page = self._get_item_detail_page(sku_id)
            if not self.parse_item_detail_page(sku_id, page):
                if retry_count > 10:
                    logger.error('无法获取cat，超出重试次数，抢购停止')
                    exit(-1)
                else:
                    logger.error('第 %s 次获取商品页信息失败：%s', page)
                    time.sleep(1)
                    continue
            else:
                cat = self.item_cat.get(sku_id)
        vender_id = self.item_vender_ids.get(sku_id)
        param_json = self.param_json.get(sku_id)
        special_attrs = self.special_attrs.get(sku_id)

        # 初始化预约抢购时间
        server_buy_time, realy_buy_time = self.init_yuyue_buy_time(sku_id, self.headers.copy(), {
            # 'callback': 'jQuery{}'.format(random.randint(1000000, 9999999)),
            'skuId': sku_id,
            'cat': cat,
            'area': area_id,
            'shopId': vender_id,
            'venderId': vender_id,
            'paramJson': param_json,
            'num': 1,
        })

        # 初始化获取商品抢购链接请求方法
        get_sku_seckill_url_request_headers = self.headers.copy()

        if fast_mode:
            get_sku_seckill_url_request_headers['Host'] = 'itemko.jd.com'

            if 'isKO' in special_attrs:
                def get_sku_seckill_url_request(sku_id, server_buy_time=int(time.time())):
                    logger.info('获取抢购链接')
                    payload = {
                        # 'callback': 'jQuery{}'.format(random.randint(1000000, 9999999)),
                        'skuId': sku_id,
                        'from': 'pc',
                        '_': str(server_buy_time * 1000),
                    }
                    get_sku_seckill_url_request_headers['Referer'] = f'https://item.jd.com/{sku_id}.html'
                    retry_interval = config.retry_interval
                    retry_count = 0
                    while not self.seckill_url.get(sku_id):
                        if retry_count >= 10:
                            logger.error("抢购链接获取失败，终止抢购！")
                            exit(-1)
                        try:
                            resp = http_util.send_http_request(self.socket_client,
                                                               url='https://itemko.jd.com/itemShowBtn',
                                                               method='GET',
                                                               headers=get_sku_seckill_url_request_headers,
                                                               params=payload
                                                               , cookies=self.get_cookies_str_by_domain_or_path(
                                    'itemko.jd.com'))
                            resp_data = resp.body
                            resp_json = parse_json(resp_data)
                            if resp_json.get('url'):
                                # https://divide.jd.com/user_routing?skuId=8654289&sn=c3f4ececd8461f0e4d7267e96a91e0e0&from=pc
                                router_url = 'https:' + resp_json.get('url')
                                # https://marathon.jd.com/captcha.html?skuId=8654289&sn=c3f4ececd8461f0e4d7267e96a91e0e0&from=pc
                                seckill_url = router_url.replace('divide', 'marathon').replace('user_routing',
                                                                                               'captcha.html')
                                logger.info("抢购链接获取成功: %s", seckill_url)
                                return seckill_url
                            else:
                                retry_count += 1
                                if resp_data:
                                    logger.info(f"响应数据：{resp_data}")
                                logger.info("商品%s第%s次获取抢购链接失败，链接为空，%s秒后重试", sku_id, retry_count, retry_interval)
                                time.sleep(retry_interval)
                        except Exception as e:
                            retry_count += 1
                            logger.error("异常信息：%s", e)
                            logger.info("商品%s第%s次获取抢购链接失败，%s秒后重试", sku_id, retry_count, retry_interval)
                            time.sleep(retry_interval)

            else:
                def get_sku_seckill_url_request(sku_id, server_buy_time=int(time.time())):
                    logger.info('获取抢购链接')
                    payload = {
                        # 'callback': 'jQuery{}'.format(random.randint(1000000, 9999999)),
                        'skuId': sku_id,
                        'cat': cat,
                        'area': area_id,
                        'shopId': vender_id,
                        'venderId': vender_id,
                        'paramJson': param_json,
                        'num': 1,
                    }
                    get_sku_seckill_url_request_headers['Referer'] = 'https://item.jd.com/'
                    retry_interval = config.retry_interval
                    retry_count = 0

                    while not self.seckill_url.get(sku_id):
                        if retry_count >= 10:
                            logger.error("抢购链接获取失败，终止抢购！")
                            exit(-1)
                        try:
                            resp = http_util.send_http_request(self.socket_client,
                                                               url='https://item-soa.jd.com/getWareBusiness',
                                                               method='GET',
                                                               headers=get_sku_seckill_url_request_headers,
                                                               params=payload,
                                                               cookies=self.get_cookies_str_by_domain_or_path(
                                                                   'item-soa.jd.com'))
                            resp_data = resp.body
                            resp_json = parse_json(resp_data)
                            yuyue_info = resp_json.get('yuyueInfo')
                            if yuyue_info:
                                # https://divide.jd.com/user_routing?skuId=8654289&sn=c3f4ececd8461f0e4d7267e96a91e0e0&from=pc
                                url = yuyue_info.get('url')
                                if url:
                                    if 'toYuyue.action' in url:
                                        retry_count += 1
                                        logger.info("商品%s正在预约中，暂未开始抢购，开始第%s次重试", sku_id, retry_count)
                                        continue
                                    router_url = 'https:' + url
                                    # https://marathon.jd.com/captcha.html?skuId=8654289&sn=c3f4ececd8461f0e4d7267e96a91e0e0&from=pc
                                    seckill_url = router_url.replace('divide', 'marathon').replace('user_routing',
                                                                                                   'captcha.html')
                                    logger.info("抢购链接获取成功: %s", seckill_url)
                                    return seckill_url
                                else:
                                    retry_count += 1
                                    if resp_data:
                                        logger.info(f"响应数据：{resp_data}")
                                    logger.info("商品%s第%s次获取抢购链接失败，链接为空，%s秒后重试", sku_id, retry_count, retry_interval)
                                    time.sleep(retry_interval)
                            else:
                                if resp_data:
                                    logger.info(f"响应数据：{resp_data}")
                                logger.info("商品%s不是 预约抢购商品 或 未开始预约，本次抢购结束", sku_id)
                                exit(-1)
                        except Exception as e:
                            retry_count += 1
                            logger.error("异常信息：%s", e)
                            logger.info("商品%s第%s次获取抢购链接失败，%s秒后重试", sku_id, retry_count, retry_interval)
                            time.sleep(retry_interval)
                    return None
        else:
            def get_sku_seckill_url_request(sku_id, server_buy_time=int(time.time())):
                url = 'https://itemko.jd.com/itemShowBtn'
                payload = {
                    'callback': 'jQuery{}'.format(random.randint(1000000, 9999999)),
                    'skuId': sku_id,
                    'from': 'pc',
                    '_': str(server_buy_time * 1000),
                }
                headers = {
                    'User-Agent': self.user_agent,
                    'Host': 'itemko.jd.com',
                    'Referer': 'https://item.jd.com/{}.html'.format(sku_id),
                }
                retry_interval = 0.2
                retry_count = 0

                while retry_count < 10:
                    try:
                        resp = self.sess.get(url=url, headers=headers, params=payload, timeout=(0.1, 0.08))
                        resp_json = parse_json(resp.text)
                        if resp_json.get('url'):
                            # https://divide.jd.com/user_routing?skuId=8654289&sn=c3f4ececd8461f0e4d7267e96a91e0e0&from=pc
                            router_url = 'https:' + resp_json.get('url')
                            # https://marathon.jd.com/captcha.html?skuId=8654289&sn=c3f4ececd8461f0e4d7267e96a91e0e0&from=pc
                            seckill_url = router_url.replace('divide', 'marathon').replace('user_routing',
                                                                                           'captcha.html')
                            logger.info("抢购链接获取成功: %s", seckill_url)
                            return seckill_url
                        else:
                            retry_count += 1
                            if resp.text:
                                logger.info(f"响应数据：{resp.text}")
                            logger.info("商品%s第%s次获取抢购链接失败，%s秒后重试", sku_id, retry_count, retry_interval)
                            time.sleep(retry_interval)
                    except Exception as e:
                        retry_count += 1
                        logger.info("异常信息：%s", e)
                        logger.info("商品%s第%s次获取抢购链接失败，%s秒后重试", sku_id, retry_count, retry_interval)
                        time.sleep(retry_interval)

                logger.error("抢购链接获取失败，终止抢购！")
                exit(-1)
        self.request_info['get_sku_seckill_url_request'] = get_sku_seckill_url_request

        # 初始化访问商品抢购链接请求方法（用于设置cookie等）
        request_sku_seckill_url_request_headers = self.headers.copy()
        if fast_mode:
            request_sku_seckill_url_request_headers['Host'] = 'marathon.jd.com'

            def request_sku_seckill_url_request(sku_id):
                logger.info('访问商品抢购链接请求')
                request_sku_seckill_url_request_headers['Referer'] = f'https://item.jd.com/{sku_id}.html'
                url = self.seckill_url.get(sku_id)
                is_pass = self.is_request_seckill_url.get(sku_id)
                if not is_pass:
                    resp = http_util.send_http_request(self.socket_client, url=url, method='GET',
                                                       headers=request_sku_seckill_url_request_headers,
                                                       cookies=self.get_cookies_str_by_domain_or_path(
                                                           'marathon.jd.com'))
                    # 从响应头中提取cookies并更新
                    cookie_util.merge_cookies_from_response(self.sess.cookies, resp, url)
                    # self.get_and_update_cookies_str()
                    self.is_request_seckill_url[sku_id] = 'pass'
                    return resp
                else:
                    return is_pass
        else:
            def request_sku_seckill_url_request(sku_id):
                headers = {
                    'User-Agent': self.user_agent,
                    'Host': 'marathon.jd.com',
                    'Referer': 'https://item.jd.com/{}.html'.format(sku_id),
                }
                return self.sess.get(url=self.seckill_url.get(sku_id), headers=headers, allow_redirects=False,
                                     timeout=(0.1, 0.08))
        self.request_info['request_sku_seckill_url_request'] = request_sku_seckill_url_request

        # 初始化访问抢购订单结算页面请求方法
        request_seckill_checkout_page_request_headers = self.headers.copy()
        # if fast_mode and is_risk_control is False:
        if fast_mode:
            # request_seckill_checkout_page_request_headers['cookie'] = self.cookies_str
            request_seckill_checkout_page_request_headers['Host'] = 'marathon.jd.com'

            def request_seckill_checkout_page_request(sku_id, num):
                logger.info('抢购订单结算页面请求')
                url = 'https://marathon.jd.com/seckill/seckill.action'
                request_sku_seckill_url_request_headers['Referer'] = f'https://item.jd.com/{sku_id}.html'
                is_pass = self.is_seckill_checkout_page.get(sku_id)
                if not is_pass:
                    resp = http_util.send_http_request(self.socket_client, url=url, method='GET',
                                                       params={
                                                           'skuId': sku_id,
                                                           'num': num,
                                                           'rid': int(time.time())
                                                       },
                                                       headers=request_seckill_checkout_page_request_headers,
                                                       cookies=self.get_cookies_str_by_domain_or_path(
                                                           'marathon.jd.com'))
                    logger.info(resp.body)
                    # 从响应头中提取cookies并更新
                    cookie_util.merge_cookies_from_response(self.sess.cookies, resp, url)
                    # self.get_and_update_cookies_str()
                    self.is_seckill_checkout_page[sku_id] = True
                    return resp
                else:
                    return is_pass
        else:
            def request_seckill_checkout_page_request(sku_id, num):
                url = 'https://marathon.jd.com/seckill/seckill.action'
                payload = {
                    'skuId': sku_id,
                    'num': num,
                    'rid': int(time.time())
                }
                headers = {
                    'User-Agent': self.user_agent,
                    'Host': 'marathon.jd.com',
                    'Referer': 'https://item.jd.com/{}.html'.format(sku_id),
                }
                self.sess.get(url=url, params=payload, headers=headers, timeout=(0.1, 0.08))
        self.request_info['request_seckill_checkout_page_request'] = request_seckill_checkout_page_request

        # 初始化获取秒杀初始化信息请求方法（包括：地址，发票，token）
        get_seckill_init_info_request_headers = self.headers.copy()
        if fast_mode:
            # get_seckill_init_info_request_headers['cookie'] = self.cookies_str
            get_seckill_init_info_request_headers['Host'] = 'marathon.jd.com'

            def get_seckill_init_info_request(sku_id, num=1):
                url = 'https://marathon.jd.com/seckillnew/orderService/pc/init.action'
                resp = http_util.send_http_request(self.socket_client, url=url, method='POST',
                                                   data={
                                                       'sku': sku_id,
                                                       'num': num,
                                                       'isModifyAddress': 'false',
                                                   },
                                                   headers=get_seckill_init_info_request_headers,
                                                   cookies=self.get_cookies_str_by_domain_or_path('marathon.jd.com'))
                # logger.info(resp.body)
                # 从响应头中提取cookies并更新
                cookie_util.merge_cookies_from_response(self.sess.cookies, resp, url)
                if resp.status == 302:
                    return resp.headers['location']
                # self.get_and_update_cookies_str()
                return resp.body
        else:
            def get_seckill_init_info_request(sku_id, num=1):
                url = 'https://marathon.jd.com/seckillnew/orderService/pc/init.action'
                data = {
                    'sku': sku_id,
                    'num': num,
                    'isModifyAddress': 'false',
                }
                headers = {
                    'User-Agent': self.user_agent,
                    'Host': 'marathon.jd.com',
                }
                return self.sess.post(url=url, data=data, headers=headers).text
        self.request_info['get_seckill_init_info_request'] = get_seckill_init_info_request

        # 初始化提交抢购（秒杀）订单请求方法
        submit_seckill_order_request_headers = self.headers.copy()
        if fast_mode:
            # submit_seckill_order_request_headers['cookie'] = cookie_str
            submit_seckill_order_request_headers['Host'] = 'marathon.jd.com'

            def submit_seckill_order_request(sku_id=None, server_buy_time=int(time.time()), num=1):
                logger.info('提交抢购（秒杀）订单请求')
                url = 'https://marathon.jd.com/seckillnew/orderService/pc/submitOrder.action'
                submit_seckill_order_request_headers[
                    'Referer'] = f'https://marathon.jd.com/seckill/seckill.action?skuId={sku_id}&num={num}&rid={server_buy_time} '
                if not self.seckill_order_data.get(sku_id):
                    self.seckill_order_data[sku_id] = self._gen_seckill_order_data(sku_id, num)

                retry_interval = 0.1
                retry_count = 0

                while retry_count < 10:
                    resp_json = None
                    try:
                        resp = http_util.send_http_request(self.socket_client, url=url, method='POST',
                                                           params={'skuId': sku_id},
                                                           data=self.seckill_order_data.get(sku_id),
                                                           headers=submit_seckill_order_request_headers,
                                                           cookies=self.get_cookies_str_by_domain_or_path(
                                                               'marathon.jd.com'))
                        body = resp.body
                        logger.info(body)
                        resp_json = parse_json(body)
                    except Exception as e:
                        logger.error('秒杀请求出错：%s', str(e))
                        retry_count += 1
                        time.sleep(retry_interval)
                    # 返回信息
                    # 抢购失败：
                    # {'errorMessage': '很遗憾没有抢到，再接再厉哦。', 'orderId': 0, 'resultCode': 60074, 'skuId': 0, 'success': False}
                    # {'errorMessage': '抱歉，您提交过快，请稍后再提交订单！', 'orderId': 0, 'resultCode': 60017, 'skuId': 0, 'success': False}
                    # {'errorMessage': '系统正在开小差，请重试~~', 'orderId': 0, 'resultCode': 90013, 'skuId': 0, 'success': False}
                    # 抢购成功：
                    # {"appUrl":"xxxxx","orderId":820227xxxxx,"pcUrl":"xxxxx","resultCode":0,"skuId":0,"success":true,"totalMoney":"xxxxx"}

                    if resp_json.get('success'):
                        order_id = resp_json.get('orderId')
                        total_money = resp_json.get('totalMoney')
                        pay_url = 'https:' + resp_json.get('pcUrl')
                        logger.info('抢购成功，订单号: %s, 总价: %s, 电脑端付款链接: %s', order_id, total_money, pay_url)
                        return True
                    else:
                        logger.info('抢购失败，返回信息: %s', resp_json)
                        retry_count += 1
                        time.sleep(retry_interval)
                return False
        else:
            def submit_seckill_order_request(sku_id, server_buy_time=int(time.time()), num=1):
                url = 'https://marathon.jd.com/seckillnew/orderService/pc/submitOrder.action'
                payload = {
                    'skuId': sku_id,
                }
                if not self.seckill_order_data.get(sku_id):
                    self.seckill_order_data[sku_id] = self._gen_seckill_order_data(sku_id, num)

                headers = {
                    'User-Agent': self.user_agent,
                    'Host': 'marathon.jd.com',
                    'Referer': 'https://marathon.jd.com/seckill/seckill.action?skuId={0}&num={1}&rid={2}'.format(
                        sku_id, num, server_buy_time),
                }

                retry_interval = 0.1
                retry_count = 0

                while retry_count < 10:
                    resp_json = None
                    try:
                        resp = self.sess.post(url=url, headers=headers, params=payload,
                                              data=self.seckill_order_data.get(sku_id), timeout=(0.1, 0.08))
                        logger.info(resp.text)
                        resp_json = parse_json(resp.text)
                    except Exception as e:
                        logger.error('秒杀请求出错：%s', str(e))
                        retry_count += 1
                        time.sleep(retry_interval)
                    # 返回信息
                    # 抢购失败：
                    # {'errorMessage': '很遗憾没有抢到，再接再厉哦。', 'orderId': 0, 'resultCode': 60074, 'skuId': 0, 'success': False}
                    # {'errorMessage': '抱歉，您提交过快，请稍后再提交订单！', 'orderId': 0, 'resultCode': 60017, 'skuId': 0, 'success': False}
                    # {'errorMessage': '系统正在开小差，请重试~~', 'orderId': 0, 'resultCode': 90013, 'skuId': 0, 'success': False}
                    # 抢购成功：
                    # {"appUrl":"xxxxx","orderId":820227xxxxx,"pcUrl":"xxxxx","resultCode":0,"skuId":0,"success":true,"totalMoney":"xxxxx"}

                    if resp_json.get('success'):
                        order_id = resp_json.get('orderId')
                        total_money = resp_json.get('totalMoney')
                        pay_url = 'https:' + resp_json.get('pcUrl')
                        logger.info('抢购成功，订单号: %s, 总价: %s, 电脑端付款链接: %s', order_id, total_money, pay_url)
                        return True
                    else:
                        logger.info('抢购失败，返回信息: %s', resp_json)
                        retry_count += 1
                        time.sleep(retry_interval)
                return False
        self.request_info['submit_seckill_order_request'] = submit_seckill_order_request
        return server_buy_time, realy_buy_time

    def new_init_seckill_request_method(self, fast_mode, is_risk_control):
        # 提前初始化请求信息、方法
        # self.get_and_update_cookies_str()
        config = self.config
        sku_id = config.sku_id

        zzz = self.item_zzz.get(sku_id)
        retry_count = 0
        item_page_resp = self.new_get_item_detail_page(sku_id)
        item_page = item_page_resp.text
        while zzz is None:
            retry_count += 1
            logger.info('加载订单')
            if not self.new_parse_item_detail_page(sku_id, item_page):
                if retry_count > 10:
                    logger.error('无法获取zzz，超出重试次数，抢购停止')
                    exit(-1)
                else:
                    logger.error('第 %s 次加载订单失败', retry_count)
                    retry_count += 1
                    time.sleep(1)
                    if item_page_resp.status_code != requests.codes.OK or not item_page:
                        item_page_resp = self.new_get_item_detail_page(sku_id)
                        item_page = item_page_resp.text
                    continue
            else:
                zzz = self.item_zzz.get(sku_id)

        area_id = parse_area_id(self.area_id)
        vender_id = self.item_vender_ids.get(sku_id)
        param_json = self.param_json.get(sku_id)
        special_attrs = self.special_attrs.get(sku_id)

        # 初始化预约抢购时间
        server_buy_time, realy_buy_time = self.new_init_yuyue_buy_time(sku_id, item_page)

        if server_buy_time > int(time.time()):
            hasYuyue_match = re.search(r'"hasYuyue":"(.*)"', item_page)
            if hasYuyue_match:
                hasYuyue = hasYuyue_match.group(1)
                if hasYuyue == '0' or hasYuyue == 0:
                    self.new_reserve(sku_id)
                elif hasYuyue == '1' or hasYuyue == 1:
                    logger.info('商品已预约，跳过自动预约')
        else:
            logger.info('商品已开售，跳过自动预约')

        # 初始化加载订单请求方法
        if fast_mode:
            get_confirm_order_page_request_headers = self.headers.copy()
            get_confirm_order_page_request_headers['Host'] = 'wq.jd.com'
            get_confirm_order_page_request_headers['dnt'] = '1'
            get_confirm_order_page_request_headers['referer'] = 'https://item.m.jd.com/'
            get_confirm_order_page_request_headers['sec-fetch-dest'] = 'document'
            get_confirm_order_page_request_headers['sec-fetch-mode'] = 'navigate'
            get_confirm_order_page_request_headers['sec-fetch-site'] = 'same-site'
            get_confirm_order_page_request_headers['sec-fetch-user'] = '?1'
            get_confirm_order_page_request_headers['upgrade-insecure-requests'] = '1'

            get_confirm_order_promise_uuid_headers = self.headers.copy()

            get_confirm_order_headers = self.headers.copy()

            def parsing_submit_page_data(html):
                data = dict()
                page_data = nested_parser('{', '}', html, 'token2')
                if '"errId":"0"' not in page_data:
                    logger.error('加载订单页数据失败，响应数据：%s', page_data)
                    raise AsstException('加载订单页数据失败')
                if isinstance(page_data, str):
                    token2search = re.search(r'"token2":\"(.*)\"', page_data)
                    if token2search:
                        data['token2'] = token2search.group(1)
                    skulistsearch = re.search(r'"skulist":\"(.*)\"', page_data)
                    if skulistsearch:
                        data['skulist'] = skulistsearch.group(1)
                    traceIdsearch = re.search(r'"traceId":\"(.*)\"', page_data)
                    if traceIdsearch:
                        data['traceid'] = traceIdsearch.group(1)
                    mainSkusearch = re.search(r'"promotion":({([^}])*})', page_data)
                    if mainSkusearch:
                        data['discountPrice'] = json.loads(mainSkusearch.group(1))['discountPrice']
                    cidsearch = re.search(r'"cid":\"(.*)\"', page_data)
                    if cidsearch:
                        data['cid'] = cidsearch.group(1).split('_')[2]
                    sucPageTypesearch = re.search(r'"sucPageType":\"(.*)\"', page_data)
                    if sucPageTypesearch:
                        data['sucPageType'] = sucPageTypesearch.group(1)
                    vender_cart = nested_parser('[', ']', page_data, '"jdShipment":')
                    if isinstance(vender_cart, str):
                        venderIdsearch = re.search(r'"venderId":\"(.*)\"', vender_cart)
                        if venderIdsearch:
                            data['venderId'] = venderIdsearch.group(1)
                        jdShipmentsearch = re.search(r'"jdShipment":\"(.*)\"', vender_cart)
                        if jdShipmentsearch:
                            data['jdShipment'] = jdShipmentsearch.group(1)
                        shipment_str = nested_inner_parser('[', ']', vender_cart, '"promiseSendPay":')
                        if isinstance(shipment_str, str):
                            shipment = json.loads(shipment_str)
                            if shipment:
                                data['shipment'] = shipment
                return data

            def parse_promise_uuid(resp_text):
                resp_json = nested_parser('{', '}', resp_text, "errId")
                if isinstance(resp_json, str):
                    ship_effect = json.loads(resp_json)
                    promise_uuid = ship_effect['pickshipment']['promiseUuid']
                elif isinstance(resp_json, list):
                    ship_effect = json.loads(resp_json[0])
                    promise_uuid = ship_effect['pickshipment']['promiseUuid']
                else:
                    promise_uuid = ''
                return promise_uuid

            def get_confirm_order_page_request(sku_id, server_buy_time=int(time.time())):
                logger.info('加载订单页面请求')
                jxsid = str(int(time.time() * 1000)) + str(random.random())[2:7]
                url = 'https://wq.jd.com/deal/confirmorder/main?jxsid=' + jxsid
                sceneval = '2'
                referer_url = f'https://item.m.jd.com/product/{sku_id}.html?sceneval={sceneval}&jxsid={jxsid}'
                commlist = f'{sku_id},,1,{sku_id},1,0,0'
                confirm_order_page_params = f'{self.item_url_param.get(sku_id)}&commlist={commlist}' \
                                            f'&wdref={parse.quote(referer_url, safe="")}'

                referer = f'{referer_url}&{confirm_order_page_params}'
                get_confirm_order_page_request_headers['Referer'] = referer_url
                get_confirm_order_promise_uuid_headers['Referer'] = referer

                if not self.get_submit_referer.get(sku_id):
                    self.get_submit_referer[sku_id] = referer

                self.sess.cookies.set('_modc', zzz)

                retry_interval = config.retry_interval
                retry_count = 0

                submit_page_data = self.get_submit_page_data.get(sku_id)
                while not submit_page_data:
                    if retry_count >= 10:
                        logger.error("加载订单页面请求失败，终止抢购！")
                        exit(-1)
                    try:
                        resp = http_util.send_http_request(self.socket_client,
                                                           url=url,
                                                           method='GET',
                                                           headers=get_confirm_order_page_request_headers,
                                                           params=confirm_order_page_params,
                                                           cookies=self.get_cookies_str_by_domain_or_path('wq.jd.com'))
                        resp_data = resp.body
                        if resp_data.startswith("<!DOCTYPE html>"):
                            submit_page_data = self.get_submit_page_data.get(sku_id)
                            if not submit_page_data:
                                submit_page_data = parsing_submit_page_data(resp_data)
                                # 从响应头中提取cookies并更新
                                cookie_util.merge_cookies_from_response(self.sess.cookies, resp, url)
                                self.get_submit_page_data[sku_id] = submit_page_data
                            break
                    except Exception as e:
                        logger.error("异常信息：%s", e)
                    retry_count += 1
                    logger.info("商品%s第%s次加载订单页面请求失败，%s秒后重试", sku_id, retry_count, retry_interval)
                    time.sleep(retry_interval)

                promise_uuid_retry_interval = 0.02
                promise_uuid = self.get_promiseUuid.get(sku_id)
                if not promise_uuid:
                    with self.sem:
                        # 订单页参数请求
                        if not self.get_promiseUuid.get(sku_id):
                            i = 0
                            while i < 8:
                                try:
                                    shipeffect_params = {
                                        'reg': 1
                                        , 'action': 1
                                        , 'reset': 1
                                        , 'callback': f'preShipeffectCb{self.letterMap[i + 1]}'
                                        , 'r': random.random()
                                        , 'sceneval': 2
                                        , 'traceid': submit_page_data.get('traceid')
                                    }
                                    logger.info('加载订单页参数请求')
                                    url = 'https://wq.jd.com/deal/mship/shipeffect'
                                    resp = http_util.send_http_request(self.socket_client,
                                                                       url=url,
                                                                       method='GET',
                                                                       headers=get_confirm_order_promise_uuid_headers,
                                                                       cookies=self.get_cookies_str_by_domain_or_path(
                                                                           'wq.jd.com'),
                                                                       params=shipeffect_params)
                                    promise_uuid = parse_promise_uuid(resp.body)
                                    if promise_uuid is not None:
                                        self.get_promiseUuid[sku_id] = promise_uuid
                                        break
                                    # 从响应头中提取cookies并更新
                                    # cookie_util.merge_cookies_from_response(self.sess.cookies, resp, url)
                                    # self.get_and_update_cookies_str()
                                except Exception as e:
                                    logger.error("异常信息：%s", e)
                                i += 1
                                logger.info("商品%s第%s次订单页参数请求失败，%s秒后重试", sku_id, i, promise_uuid_retry_interval)
                                time.sleep(promise_uuid_retry_interval)

                submit_data = self.get_submit_data.get(sku_id)
                if not submit_data:
                    with self.sem:
                        # 订单参数处理
                        if not self.get_submit_data.get(sku_id):
                            discountPrice = submit_page_data.pop('discountPrice', '')
                            cid = submit_page_data.pop('cid', '')
                            shipment = submit_page_data.pop('shipment', '')
                            venderId = submit_page_data.pop('venderId', '')
                            jdShipment = submit_page_data.pop('jdShipment', '')

                            params_list = []
                            params_list.append(
                                'paytype=0&paychannel=1&action=1&reg=1&type=0&gpolicy=&platprice=0&pick=&savepayship=0&sceneval=2&setdefcoupon=0')
                            params_list.append('&tuanfull=')
                            params_list.append(submit_page_data.pop('sucPageType', ''))
                            for key, value in submit_page_data.items():
                                params_list.append(f'&{key}={value}')
                            params_list.append(f'&valuableskus={sku_id},{config.num},{discountPrice},{cid}')
                            params_list.append(f'&commlist={commlist}')
                            params_list.append('&dpid=&scan_orig=')

                            # params_list.append(f'&dpid={?}')
                            # params_list.append(f'&scan_orig={?}')

                            # 处理shipment
                            shipmentData = None
                            shipName = None
                            shipType = '0'
                            for i, data in enumerate(shipment):
                                shipType = data.get('type')
                                if shipType == '0':
                                    shipmentData = data
                                    shipName = ["jd311", "jdjzd", "jd411"][i]
                                    break
                                elif shipType == '1' \
                                        or shipType == '2':
                                    shipmentData = data
                                    shipName = "shipsop"
                                    break
                                elif shipType == '3' \
                                        or shipType == '6':
                                    # var _ = new K.default(e,n,t,h,i);
                                    # _.supported ? u[_.name] = _ : p[_.name] = _;
                                    break
                                elif shipType == '4':
                                    # "1" == n.selected && "0" == e.jdShipment && (e.isTenVideo = !0,
                                    # h.isTenVideo = !0,
                                    # h.fpbarTipLoc = e.isloc,
                                    # h.fpbarTipTen = !e.isloc);
                                    break
                                elif shipType == '5':
                                    # var g, y, b = !1;
                                    # if (ce.supSopJd = !0,
                                    # e.smallProducts.length > 0)
                                    #     (0,
                                    #     D.default)(g = oe.smallShipments).call(g, function(a) {
                                    #         var r = new a(e,n,t,h,i);
                                    #         r.supported ? u[r.name] = r : p[r.name] = r
                                    #     });
                                    # if (e.laProducts.length > 0)
                                    #     (0,
                                    #     D.default)(y = oe.largeShipments).call(y, function(a) {
                                    #         var r = new a(e,n,t,h,i);
                                    #         r.supported ? (u[r.name] = r,
                                    #         b = !0) : p[r.name] = r
                                    #     });
                                    # if (e.laProducts.length > 0) {
                                    #     var w = new U.default(e,n,t,h,i);
                                    #     w.supported && !b ? u[w.name] = w : p[w.name] = w
                                    # }
                                    break
                                elif shipType == '7':
                                    # if ("1" == n.supported) {
                                    #     var S = new G.default(e,n,t,h,i);
                                    #     S.supported ? u[S.name] = S : p[S.name] = S
                                    # }
                                    break
                                elif shipType == '8':
                                    # var x = new F.default(e,n,t,h,i);
                                    # x.supported && (u[x.name] = x);
                                    break
                                elif shipType == '9':
                                    # var P = new M.default(e,n,t,h,i);
                                    # P.supported ? u[P.name] = P : p[P.name] = P;
                                    break
                                elif shipType == '10':
                                    # var j = new H.default(e,n,t,h,i);
                                    # j.supported ? u[j.name] = j : p[j.name] = j
                                    break
                                # else:
                                #     break

                            # if not shipmentData:
                            #     raise AsstException('抢购失败，无法获取订单页收获地址数据，本次抢购结束')
                            #     exit(-1)
                            if shipmentData.get('selected') != '1':
                                raise AsstException('抢购失败，订单页收获地址未自动选择，本次抢购结束')
                                exit(-1)

                            ship_list = None
                            promise_uuid_index = None
                            if shipType == '0':
                                ship_list = [''] * 25
                                promise_uuid_index = 22
                            elif shipType == '1':
                                ship_list = [''] * 9
                                promise_uuid_index = 7
                            elif shipType == '2' \
                                    or shipType == '5' \
                                    or shipType == '9':
                                ship_list = [''] * 20
                                promise_uuid_index = 17
                            elif shipType == '8':
                                ship_list = [''] * 10
                                promise_uuid_index = 8
                            elif shipType == '10':
                                ship_list = [''] * 5
                                promise_uuid_index = 4
                            else:
                                ship_list = [''] * 25
                                promise_uuid_index = 22

                            shipId = shipmentData.get('id')

                            ship_list[0] = shipType
                            ship_list[1] = shipId
                            if shipType in ['1', '2', '5', '9', '10']:
                                ship_list[2] = venderId
                            elif shipType == '8':
                                ship_list[2] = '0'
                            else:
                                ship_list[17] = '0'
                            ship_list[promise_uuid_index] = promise_uuid

                            if shipType == '0':
                                # 处理shipName
                                if shipName == 'jd311':
                                    ship_list[2] = '4'
                                    ship_list[7] = '1'
                                    ship_list[9] = shipmentData.get('promiseDate')
                                    ship_list[10] = shipmentData.get('promiseTimeRange')
                                    ship_list[11] = shipmentData.get('promiseSendPay')
                                    ship_list[12] = shipmentData.get('batchId')
                                    ship_list[20] = ''
                                elif shipName == 'jdjzd':
                                    ship_list[2] = '6'
                                    ship_list[7] = '3'
                                    ship_list[9] = shipmentData.get('promiseDate')
                                    ship_list[10] = shipmentData.get('promiseTimeRange')
                                    ship_list[11] = shipmentData.get('promiseSendPay')
                                    ship_list[12] = shipmentData.get('batchId')
                                    # t.calendarTag
                                    ship_list[18] = ''  # t.calendarTag
                                    # && t.calendarTag.length
                                    # && (0, r.default)(y=t.calendarTag).call(y, function(e){return e.selected}).tagType || ""
                                    ship_list[20] = ''
                                elif shipName == 'jd411':
                                    ship_list[2] = '5'
                                    ship_list[7] = '2'
                                    ship_list[11] = shipmentData.get('promiseSendPay')
                                ship_list[5] = '0'
                                ship_list[19] = '0'
                                ship_list[21] = '0'
                                ship_list[24] = ''
                            elif shipType == '2':
                                if shipmentData:
                                    ship_list[3] = shipmentData.get('promiseDate')
                                    ship_list[4] = shipmentData.get('promiseTimeRange')
                                    ship_list[5] = shipmentData.get('promiseSendPay')
                                    ship_list[6] = shipmentData.get('batchId')
                                else:
                                    ship_list[3] = ''
                                    ship_list[4] = ''
                                    ship_list[5] = ''
                                    ship_list[6] = ''

                            elif shipType == '3' \
                                    or shipType == '6':
                                pass

                            elif shipType == '5':
                                if shipmentData:
                                    ship_list[3] = shipmentData.get('promiseDate')
                                    ship_list[4] = shipmentData.get('promiseTimeRange')
                                    ship_list[5] = shipmentData.get('promiseSendPay')
                                    ship_list[6] = shipmentData.get('batchId')
                                else:
                                    ship_list[3] = ''
                                    ship_list[4] = ''
                                    ship_list[5] = ''
                                    ship_list[6] = ''
                                ship_list[15] = "1"
                                if "shipsopjzd" == shipName:
                                    ship_list[15] = "2"
                                ship_list[16] = ''# t.calendarTag
                                # && t.calendarTag.length
                                # && (0, c.default)(w=t.calendarTag).call(w, function(e){return e.selected}).tagType | | "";
                                ship_list[13] = '0'
                                ship_list[19] = ''

                            elif shipType == '7':
                                pass

                            elif shipType == '8':
                                if shipmentData:
                                    timeRange = shipmentData.get('promiseTimeRange')
                                    ship_list[3] = shipmentData.get('promiseDate')
                                    ship_list[4] = timeRange
                                    ship_list[5] = shipmentData.get('promiseSendPay')
                                    ship_list[6] = shipmentData.get('batchId')
                                    if '立即送达' in timeRange:
                                        ship_list[7] = '1'
                                    else:
                                        ship_list[7] = '2'
                                else:
                                    ship_list[3] = ''
                                    ship_list[4] = ''
                                    ship_list[5] = ''
                                    ship_list[6] = ''

                            elif shipType == '9':
                                if shipmentData:
                                    timeRange = shipmentData.get('promiseTimeRange')
                                    ship_list[3] = shipmentData.get('promiseDate')
                                    if '下单' in timeRange:
                                        ship_list[4] = '立即送达'
                                    elif timeRange:
                                        ship_list[4] = timeRange
                                    else:
                                        ship_list[4] = ''
                                    ship_list[5] = shipmentData.get('promiseSendPay')
                                    ship_list[6] = shipmentData.get('batchId')
                                    if '下单' in timeRange:
                                        ship_list[14] = '1'
                                    elif timeRange:
                                        ship_list[14] = '2'
                                    else:
                                        ship_list[14] = ''
                                else:
                                    ship_list[3] = ''
                                    ship_list[4] = ''
                                    ship_list[5] = ''
                                    ship_list[6] = ''
                                    ship_list[14] = ''
                            elif shipType == '10':
                                pass
                            else:
                                pass

                            params_list.append(f'&ship={parse.quote("|".join(ship_list), safe="{|,:}")}')

                            submit_data = ''.join(params_list)
                            if submit_data:
                                # 保存submit_data
                                self.get_submit_data[sku_id] = submit_data
                        return submit_data

            def submit_order_request(submit_data, count):
                # 新提交订单请求
                logger.info('提交订单请求')
                submit_data = f'{submit_data}&r={random.random()}&callback=confirmCb{self.letterMap[count]}'
                get_confirm_order_headers['Referer'] = self.get_submit_referer.get(sku_id)
                try:
                    resp = http_util.send_http_request(self.socket_client,
                                                       url='https://wq.jd.com/deal/msubmit/confirm',
                                                       method='GET',
                                                       headers=get_confirm_order_headers,
                                                       cookies=self.get_cookies_str_by_domain_or_path('wq.jd.com'),
                                                       params=submit_data)
                    response_data = resp.body
                    if resp.status == requests.codes.OK:
                        if response_data:
                            if '"errId":"0"' in response_data:
                                logger.info('订单提交完成，在手机APP中可以查看是否完成下单')
                                return True
                            else:
                                logger.info('订单提交失败')
                                logger.info(f'响应数据：\n{response_data}')
                                return False
                        else:
                            logger.info('订单提交失败，响应码：%s', resp.status)
                            return False
                    else:
                        logger.info('订单提交失败，响应码：%s', resp.status)
                        logger.info(f'响应数据：\n{response_data}')
                        return False
                except Exception as e:
                    logger.error(e)
                    return False

        else:
            def get_confirm_order_page_request(sku_id, server_buy_time=int(time.time())):
                exit(-1)

            def submit_order_request(submit_data, count):
                exit(-1)

        self.request_info['get_confirm_order_page_request'] = get_confirm_order_page_request
        self.request_info['submit_order_request'] = submit_order_request

        return server_buy_time, realy_buy_time

    @check_login
    def buy_item_in_stock(self, sku_ids, area, wait_all=False, stock_interval=3, submit_retry=3, submit_interval=5):
        """根据库存自动下单商品
        :param sku_ids: 商品id。可以设置多个商品，也可以带数量，如：'1234' 或 '1234,5678' 或 '1234:2' 或 '1234:2,5678:3'
        :param area: 地区id
        :param wait_all: 是否等所有商品都有货才一起下单，可选参数，默认False
        :param stock_interval: 查询库存时间间隔，可选参数，默认3秒
        :param submit_retry: 提交订单失败后重试次数，可选参数，默认3次
        :param submit_interval: 提交订单失败后重试时间间隔，可选参数，默认5秒
        :return:
        """
        items_dict = parse_sku_id(sku_ids)
        items_list = list(items_dict.keys())
        area_id = parse_area_id(area=area)

        if not wait_all:
            logger.info('下单模式：%s 任一商品有货并且未下架均会尝试下单', items_list)
            while True:
                for (sku_id, count) in items_dict.items():
                    if not self.if_item_can_be_ordered(sku_ids={sku_id: count}, area=area_id):
                        logger.info('%s 不满足下单条件，%ss后进行下一次查询', sku_id, stock_interval)
                    else:
                        logger.info('%s 满足下单条件，开始执行', sku_id)
                        self._cancel_select_all_cart_item()
                        self._add_or_change_cart_item(self.get_cart_detail(), sku_id, count)
                        if self.submit_order_with_retry(submit_retry, submit_interval):
                            return

                    time.sleep(stock_interval)
        else:
            logger.info('下单模式：%s 所有都商品同时有货并且未下架才会尝试下单', items_list)
            while True:
                if not self.if_item_can_be_ordered(sku_ids=sku_ids, area=area_id):
                    logger.info('%s 不满足下单条件，%ss后进行下一次查询', items_list, stock_interval)
                else:
                    logger.info('%s 满足下单条件，开始执行', items_list)
                    self._cancel_select_all_cart_item()
                    shopping_cart = self.get_cart_detail()
                    for (sku_id, count) in items_dict.items():
                        self._add_or_change_cart_item(shopping_cart, sku_id, count)

                    if self.submit_order_with_retry(submit_retry, submit_interval):
                        return

                time.sleep(stock_interval)

    @check_login
    def exec_reserve_seckill_by_time(self, config):
        """定时抢购`预约抢购商品`

        一定要确保预约的商品在购物车中才能使用这种方式！！！否则只能用其他方式

        预约抢购商品特点：
            1.需要提前点击预约
            2.大部分此类商品在预约后自动加入购物车，在购物车中可见但无法勾选✓，也无法进入到结算页面（重要特征）
            3.到了抢购的时间点后，才能勾选并结算下单

        注意：
            1.请在抢购开始前手动清空购物车中此类无法勾选的商品！（因为脚本在执行清空购物车操作时，无法清空不能勾选的商品）
        """

        if not config:
            raise AsstException('初始化配置为空！')

        self.config = config

        # 开抢前清空购物车
        self.clear_cart()

        sku_id = config.sku_id
        area_id = parse_area_id(self.area_id)
        cat = self.item_cat.get(sku_id)
        retry_count = 0
        while not cat:
            retry_count += 1
            logger.info('第 %s 次获取商品页信息', retry_count)
            page = self._get_item_detail_page(sku_id)
            if not self.parse_item_detail_page(sku_id, page):
                if retry_count > 10:
                    logger.error('无法获取cat，超出重试次数，抢购停止')
                    exit(-1)
                else:
                    logger.error('第 %s 次获取商品页信息失败：%s', page)
                    time.sleep(1)
                    continue
            else:
                cat = self.item_cat.get(sku_id)
        vender_id = self.item_vender_ids.get(sku_id)
        param_json = self.param_json.get(sku_id)
        # special_attrs = self.special_attrs.get(sku_id)

        # [前置]初始化预约抢购时间
        server_buy_time, realy_buy_time = self.init_yuyue_buy_time(sku_id, self.headers.copy(), {
            # 'callback': 'jQuery{}'.format(random.randint(1000000, 9999999)),
            'skuId': sku_id,
            'cat': cat,
            'area': area_id,
            'shopId': vender_id,
            'venderId': vender_id,
            'paramJson': param_json,
            'num': 1,
        })

        # 1.初始化正常下单流程请求信息、方法
        self.init_default_order_request_method(config.fast_mode, config.is_risk_control)

        def start_func():

            # 3.执行
            if config.is_pass_cart is not True:
                sku_ids = {config.sku_id: config.num}
                add_cart_request = self.request_info['add_cart_request']

                for sku_id, count in parse_sku_id(sku_ids=sku_ids).items():
                    payload = {
                        'pid': sku_id,
                        'pcount': count,
                        'ptype': 1,
                    }
                    add_cart_request(payload)

            # 获取订单结算页面信息
            self.get_checkout_page_detail()

            retry = config.retry
            interval = config.interval
            for count in range(1, retry + 1):
                logger.info('第[%s/%s]次尝试提交订单', count, retry)
                if self.submit_order():
                    break
                logger.info('休息%ss', interval)
                time.sleep(interval)
            else:
                logger.info('执行结束，提交订单失败！')

        self.start_func = start_func

        # 2.倒计时
        logger.info('准备抢购商品id为：%s', config.sku_id)

        Timer(buy_time=realy_buy_time, sleep_interval=config.sleep_interval,
              fast_sleep_interval=config.fast_sleep_interval, is_sync=False, assistant=self).start()

        if self.config.fast_mode:
            self.close_now()

    # 初始化下单必须参数
    def init_order_request_info(self):
        # 获取下单必须参数

        br = self.br

        # 获取：ipLoc-djd、ipLocation
        if address_util.get_user_address(self) is not True:
            logger.error('获取地址信息失败，请重试！')
            exit(-1)

        if self.use_new:
            # 获取：eid、fp、jstub、token、sdkToken（默认为空）
            def jsCallback(data):
                # print(data)
                self.data = data
                if len(data) > 0:
                    logger.info('自动初始化下单参数成功！')
                    return True
                return False

            jsFunc = CustomBrowser.JsScript('return (function(){var obj={};for(var count=0;count<20;count++){'
                                            'try{obj=getJdEid()}catch(e){count++;sleep(500)}};return obj})()',
                                            jsCallback)

            count = 0
            while True:
                if br.openUrl('https://idt.jd.com/paypwd/toUpdateOrForget/', jsFunc):
                    if not len(self.data) > 0:
                        if count > 3:
                            logger.error(
                                '初始化下单参数失败！请在 config.ini 中配置 eid, fp, track_id, risk_control 参数，具体请参考 wiki-常见问题')
                            exit(-1)
                    else:
                        break
                else:
                    if count > 3:
                        logger.error('初始化下单参数失败！请在 config.ini 中配置 eid, fp, track_id, risk_control 参数，具体请参考 wiki-常见问题')
                        exit(-1)
                count += 1
                logger.info('初始化下单参数失败！开始第 %s 次重试', count)
        else:
            # 获取：eid、fp、track_id、risk_control（默认为空）

            def jsCallback(data):
                # print(data)
                eid = data['eid']
                fp = data['fp']
                track_id = data['trackId']
                if eid:
                    self.eid = eid
                if fp:
                    self.fp = fp
                if track_id:
                    self.track_id = track_id
                if eid and fp and track_id:
                    logger.info('自动初始化下单参数成功！')
                    return True
                return False

            jsFunc = CustomBrowser.JsScript('return (function(){var getCookie=function(name){'
                                            'var arr,reg=new RegExp("(^| )"+name+"=([^;]*)(;|$)");'
                                            'if(arr=document.cookie.match(reg)){return unescape(arr[2]);}else{return '
                                            'null;}},obj={eid:"",fp:"",trackId:""};for(var count=0;count<20;count++){'
                                            'try{getJdEid(function(eid, fp, udfp){var trackId=getCookie("TrackID");'
                                            'if(eid&&fp&&trackId){obj.eid=eid;obj.fp=fp;obj.trackId=trackId;return obj;}'
                                            'else{count++;sleep(500)}})}catch(e){count++;sleep(500)}};return obj})()',
                                            jsCallback)

            # headers = {
            #     # 'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            #     'accept-encoding': 'gzip, deflate, br',
            #     'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            #     'cache-control': 'max-age=0',
            #     'dnt': '1',
            #     'sec-fetch-dest': 'document',
            #     'sec-fetch-mode': 'navigate',
            #     'sec-fetch-site': 'none',
            #     'sec-fetch-user': '?1',
            #     'upgrade-insecure-requests': '1',
            # }

            count = 0
            while True:
                if br.openUrl('https://order.jd.com/center/list.action', jsFunc):
                    if not self.eid or not self.fp or not self.track_id:
                        if count > 3:
                            logger.error(
                                '初始化下单参数失败！请在 config.ini 中配置 eid, fp, track_id, risk_control 参数，具体请参考 wiki-常见问题')
                            exit(-1)
                    else:
                        break
                else:
                    if count > 3:
                        logger.error('初始化下单参数失败！请在 config.ini 中配置 eid, fp, track_id, risk_control 参数，具体请参考 wiki-常见问题')
                        exit(-1)
                count += 1
                logger.info('初始化下单参数失败！开始第 %s 次重试', count)
        if br:
            # 关闭浏览器
            br.quit()

    def init_default_order_request_method(self, fast_mode, is_risk_control):
        # 提前初始化请求信息、方法
        # self.get_and_update_cookies_str()
        # config = self.config
        # 初始化添加购物车请求方法
        add_cart_request_headers = self.headers.copy()
        if fast_mode:
            # add_cart_request_headers['cookie'] = cookie_str

            def add_cart_request(params):
                # 为提高性能，并发时先校验一次，不满足再进入锁
                if not self.is_add_cart_request.get(0):
                    i = 0
                    while i < 3:
                        with self.sem:
                            # 进入锁后，需进行二次校验，要确保只请求了一次
                            if not self.is_add_cart_request.get(0):
                                logger.info('添加购物车请求')
                                try:
                                    def res_func(_conn):
                                        while True:
                                            data = _conn.recv(1)
                                            _conn.invalidate()
                                            logger.info('添加购物车请求已接收-为提高抢购速度，已截断响应数据')
                                            return None

                                    url = 'https://cart.jd.com/gate.action'
                                    resp = http_util.send_http_request(self.socket_client,
                                                                       url=url,
                                                                       method='GET',
                                                                       headers=add_cart_request_headers,
                                                                       cookies=self.get_cookies_str_by_domain_or_path(
                                                                           'cart.jd.com'),
                                                                       params=params, res_func=res_func)
                                    self.is_add_cart_request[0] = True
                                    # 从响应头中提取cookies并更新
                                    # cookie_util.merge_cookies_from_response(self.sess.cookies, resp, url)
                                    # self.get_and_update_cookies_str()
                                    break
                                except Exception as e:
                                    i += 1
                                    logger.error('添加购物车请求异常，开始第 %s 次重试，信息：%s', i, e)
                            else:
                                break
        else:
            def add_cart_request(params):
                i = 0
                while i < 3:
                    try:
                        resp = self.sess.get(url='https://cart.jd.com/gate.action',
                                             headers=add_cart_request_headers, params=params,
                                             timeout=(0.2, 0.03))
                        if 'https://cart.jd.com/cart.action' in resp.url:  # 套装商品加入购物车后直接跳转到购物车页面
                            result = True
                        else:  # 普通商品成功加入购物车后会跳转到提示 "商品已成功加入购物车！" 页面
                            soup = BeautifulSoup(resp.text, "html.parser")
                            result = bool(soup.select('h3.ftx-02'))  # [<h3 class="ftx-02">商品已成功加入购物车！</h3>]

                        if result:
                            logger.info('%s 已成功加入购物车', params['pid'])
                            break
                        else:
                            i += 1
                            logger.error('%s 添加购物车失败，开始第 %s 次重试', params['pid'], i)
                            logger.error('响应数据：%s', resp)
                    except requests.exceptions.ConnectTimeout as e:
                        i += 1
                        logger.error('%s 添加购物车请求发送超时，开始第 %s 次重试', params['pid'], i)
                    except requests.exceptions.ReadTimeout as e:
                        logger.info('已发送添加到购物车请求，为提高抢购速度，已截断响应数据')
                        break

        self.request_info['add_cart_request'] = add_cart_request

        get_checkout_page_request_headers = self.headers.copy()
        # 初始化订单结算页请求方法
        if fast_mode and is_risk_control is False:
            # get_checkout_page_request_headers['cookie'] = cookie_str

            def get_checkout_page_request(params):
                logger.info('订单结算请求')
                i = 0

                def res_func(conn):
                    while True:
                        data = conn.recv(1)
                        conn.invalidate()
                        logger.info('订单结算请求已接收-为提高抢购速度，已截断响应数据')
                        return None

                if not self.is_get_checkout_page.get(0):
                    while i < 3:
                        try:

                            url = 'https://trade.jd.com/shopping/order/getOrderInfo.action'
                            resp = http_util.send_http_request(self.socket_client,
                                                               url=url,
                                                               method='GET',
                                                               headers=get_checkout_page_request_headers,
                                                               cookies=self.get_cookies_str_by_domain_or_path(
                                                                   'trade.jd.com'),
                                                               params=params, res_func=res_func)
                            self.is_get_checkout_page[0] = True
                            # 从响应头中提取cookies并更新
                            # cookie_util.merge_cookies_from_response(self.sess.cookies, resp, url)
                            # self.get_and_update_cookies_str()
                            break
                        except Exception as e:
                            i += 1
                            logger.error('订单结算请求错误，开始第 %s 次重试，信息：%s', i, e)
        else:
            def get_checkout_page_request(params):
                i = 0
                resp = None
                while i < 3:
                    try:
                        # url = 'https://cart.jd.com/gotoOrder.action'
                        resp = self.sess.get(url='https://trade.jd.com/shopping/order/getOrderInfo.action',
                                             headers=get_checkout_page_request_headers, params=params,
                                             timeout=(0.2, 0.07))
                        if not response_status(resp):
                            logger.error('获取订单结算页信息失败')
                            return

                        soup = BeautifulSoup(resp.text, "html.parser")
                        self.risk_control = get_tag_value(soup.select('input#riskControl'), 'value')

                        # order_detail = {
                        #     'address': soup.find('span', id='sendAddr').text[5:],  # remove '寄送至： ' from the begin
                        #     'receiver': soup.find('span', id='sendMobile').text[4:],  # remove '收件人:' from the begin
                        #     'total_price': soup.find('span', id='sumPayPriceId').text[1:],  # remove '￥' from the begin
                        #     'items': []
                        # }
                        # T O D O: 这里可能会产生解析问题，待修复
                        # for item in soup.select('div.goods-list div.goods-items'):
                        #     div_tag = item.select('div.p-price')[0]
                        #     order_detail.get('items').append({
                        #         'name': get_tag_value(item.select('div.p-name a')),
                        #         'price': get_tag_value(div_tag.select('strong.jd-price'))[2:],  # remove '￥ ' from the begin
                        #         'num': get_tag_value(div_tag.select('span.p-num'))[1:],  # remove 'x' from the begin
                        #         'state': get_tag_value(div_tag.select('span.p-state'))  # in stock or out of stock
                        #     })

                        # logger.info("下单信息：%s", order_detail)
                        # return order_detail
                        return
                    except requests.exceptions.ConnectTimeout as e:
                        i += 1
                        logger.error('订单结算页面数据连接超时，开始第 %s 次重试', i)
                    except requests.exceptions.ReadTimeout as e:
                        logger.info('已发送订单结算请求，为提高抢购速度，已截断响应数据')
                        break
                    except Exception as e:
                        logger.error('订单结算页面数据解析异常（可以忽略），报错信息：%s', e)
                        if resp:
                            logger.error('resp.text：%s', resp.text)
                        break

        self.request_info['get_checkout_page_request'] = get_checkout_page_request

        # 初始化提交订单请求方法
        submit_order_request_data = {
            'overseaPurchaseCookies': '',
            'vendorRemarks': '[]',
            'submitOrderParam.sopNotPutInvoice': 'false',
            'submitOrderParam.trackID': 'TestTrackId',
            'submitOrderParam.ignorePriceChange': '0',
            'submitOrderParam.btSupport': '0',
            'riskControl': self.risk_control,
            'submitOrderParam.isBestCoupon': 1,
            'submitOrderParam.jxj': 1,
            'submitOrderParam.trackId': self.track_id,  # T o d o: need to get trackId
            'submitOrderParam.eid': self.eid,
            'submitOrderParam.fp': self.fp,
            'submitOrderParam.needCheck': 1
        }
        submit_order_request_headers = {
            'User-Agent': self.user_agent,
            'Host': 'trade.jd.com',
            'Referer': 'https://trade.jd.com/shopping/order/getOrderInfo.action'
        }
        # 如果有密码则设置
        payment_pwd = global_config.get('account', 'payment_pwd')
        if payment_pwd:
            submit_order_request_data['submitOrderParam.payPassword'] = encrypt_payment_pwd(payment_pwd)

        if fast_mode:
            # submit_order_request_headers['cookie'] = cookie_str

            def submit_order_request():
                submit_order_request_data['riskControl'] = self.risk_control
                logger.info('提交订单请求')
                try:
                    resp = http_util.send_http_request(self.socket_client,
                                                       url='https://trade.jd.com/shopping/order/submitOrder.action',
                                                       method='POST',
                                                       headers=submit_order_request_headers,
                                                       cookies=self.get_cookies_str_by_domain_or_path('trade.jd.com'),
                                                       data=submit_order_request_data)
                    response_data = resp.body
                    if response_data:
                        try:
                            resp_json = json.loads(response_data)
                            if resp_json.get('success'):
                                order_id = resp_json.get('orderId')
                                logger.info('订单提交成功! 订单号：%s', order_id)
                                if self.send_message:
                                    self.messenger.send(text='jd-assistant 订单提交成功', desp='订单号：%s' % order_id)
                                return True
                            else:
                                message, result_code = resp_json.get('message'), resp_json.get('resultCode')
                                if result_code == 0:
                                    message = message + '(下单失败)'
                                    # self._save_invoice()
                                    # message = message + '(下单商品可能为第三方商品，将切换为普通发票进行尝试)'
                                elif result_code == 60077:
                                    message = message + '(可能是购物车为空 或 未勾选购物车中商品)'
                                elif result_code == 60123:
                                    message = message + '(需要在config.ini文件中配置支付密码)'
                                elif result_code == 600158:
                                    logger.info('订单提交失败, 错误码：%s, 返回信息：%s', result_code, message)
                                    logger.info(f'很抱歉，您抢购的商品无货！本次抢购结束')
                                    return True
                                logger.info('订单提交失败, 错误码：%s, 返回信息：%s', result_code, message)
                                logger.info(f'响应数据：\n{resp_json}')
                                return False
                        except Exception:
                            logger.info('数据解析异常，响应数据：\n %s', response_data)
                            return False
                    else:
                        logger.info('下单请求异常，无响应数据')
                        return False
                except Exception as e:
                    logger.error(e)
                    return False
        else:
            def submit_order_request():
                try:
                    submit_order_request_data['riskControl'] = self.risk_control
                    resp = self.sess.post(url='https://trade.jd.com/shopping/order/submitOrder.action',
                                          headers=submit_order_request_headers, data=submit_order_request_data)
                    # 暂时不设置超时时间
                    # resp = self.sess.post(url=url, data=data, headers=headers, timeout=(0.1, 0.08))
                    resp_json = json.loads(resp.text)

                    # 返回信息示例：
                    # 下单失败
                    # {'overSea': False, 'orderXml': None, 'cartXml': None, 'noStockSkuIds': '', 'reqInfo': None, 'hasJxj': False, 'addedServiceList': None, 'sign': None, 'pin': 'xxx', 'needCheckCode': False, 'success': False, 'resultCode': 60123, 'orderId': 0, 'submitSkuNum': 0, 'deductMoneyFlag': 0, 'goJumpOrderCenter': False, 'payInfo': None, 'scaleSkuInfoListVO': None, 'purchaseSkuInfoListVO': None, 'noSupportHomeServiceSkuList': None, 'msgMobile': None, 'addressVO': None, 'msgUuid': None, 'message': '请输入支付密码！'}
                    # {'overSea': False, 'cartXml': None, 'noStockSkuIds': '', 'reqInfo': None, 'hasJxj': False, 'addedServiceList': None, 'orderXml': None, 'sign': None, 'pin': 'xxx', 'needCheckCode': False, 'success': False, 'resultCode': 60017, 'orderId': 0, 'submitSkuNum': 0, 'deductMoneyFlag': 0, 'goJumpOrderCenter': False, 'payInfo': None, 'scaleSkuInfoListVO': None, 'purchaseSkuInfoListVO': None, 'noSupportHomeServiceSkuList': None, 'msgMobile': None, 'addressVO': None, 'msgUuid': None, 'message': '您多次提交过快，请稍后再试'}
                    # {'overSea': False, 'orderXml': None, 'cartXml': None, 'noStockSkuIds': '', 'reqInfo': None, 'hasJxj': False, 'addedServiceList': None, 'sign': None, 'pin': 'xxx', 'needCheckCode': False, 'success': False, 'resultCode': 60077, 'orderId': 0, 'submitSkuNum': 0, 'deductMoneyFlag': 0, 'goJumpOrderCenter': False, 'payInfo': None, 'scaleSkuInfoListVO': None, 'purchaseSkuInfoListVO': None, 'noSupportHomeServiceSkuList': None, 'msgMobile': None, 'addressVO': None, 'msgUuid': None, 'message': '获取用户订单信息失败'}
                    # {"cartXml":null,"noStockSkuIds":"xxx","reqInfo":null,"hasJxj":false,"addedServiceList":null,"overSea":false,"orderXml":null,"sign":null,"pin":"xxx","needCheckCode":false,"success":false,"resultCode":600157,"orderId":0,"submitSkuNum":0,"deductMoneyFlag":0,"goJumpOrderCenter":false,"payInfo":null,"scaleSkuInfoListVO":null,"purchaseSkuInfoListVO":null,"noSupportHomeServiceSkuList":null,"msgMobile":null,"addressVO":{"pin":"xxx","areaName":"","provinceId":xx,"cityId":xx,"countyId":xx,"townId":xx,"paymentId":0,"selected":false,"addressDetail":"xx","mobile":"xx","idCard":"","phone":null,"email":null,"selfPickMobile":null,"selfPickPhone":null,"provinceName":null,"cityName":null,"countyName":null,"townName":null,"giftSenderConsigneeName":null,"giftSenderConsigneeMobile":null,"gcLat":0.0,"gcLng":0.0,"coord_type":0,"longitude":0.0,"latitude":0.0,"selfPickOptimize":0,"consigneeId":0,"selectedAddressType":0,"siteType":0,"helpMessage":null,"tipInfo":null,"cabinetAvailable":true,"limitKeyword":0,"specialRemark":null,"siteProvinceId":0,"siteCityId":0,"siteCountyId":0,"siteTownId":0,"skuSupported":false,"addressSupported":0,"isCod":0,"consigneeName":null,"pickVOname":null,"shipmentType":0,"retTag":0,"tagSource":0,"userDefinedTag":null,"newProvinceId":0,"newCityId":0,"newCountyId":0,"newTownId":0,"newProvinceName":null,"newCityName":null,"newCountyName":null,"newTownName":null,"checkLevel":0,"optimizePickID":0,"pickType":0,"dataSign":0,"overseas":0,"areaCode":null,"nameCode":null,"appSelfPickAddress":0,"associatePickId":0,"associateAddressId":0,"appId":null,"encryptText":null,"certNum":null,"used":false,"oldAddress":false,"mapping":false,"addressType":0,"fullAddress":"xxxx","postCode":null,"addressDefault":false,"addressName":null,"selfPickAddressShuntFlag":0,"pickId":0,"pickName":null,"pickVOselected":false,"mapUrl":null,"branchId":0,"canSelected":false,"address":null,"name":"xxx","message":null,"id":0},"msgUuid":null,"message":"xxxxxx商品无货"}
                    # {'orderXml': None, 'overSea': False, 'noStockSkuIds': 'xxx', 'reqInfo': None, 'hasJxj': False, 'addedServiceList': None, 'cartXml': None, 'sign': None, 'pin': 'xxx', 'needCheckCode': False, 'success': False, 'resultCode': 600158, 'orderId': 0, 'submitSkuNum': 0, 'deductMoneyFlag': 0, 'goJumpOrderCenter': False, 'payInfo': None, 'scaleSkuInfoListVO': None, 'purchaseSkuInfoListVO': None, 'noSupportHomeServiceSkuList': None, 'msgMobile': None, 'addressVO': {'oldAddress': False, 'mapping': False, 'pin': 'xxx', 'areaName': '', 'provinceId': xx, 'cityId': xx, 'countyId': xx, 'townId': xx, 'paymentId': 0, 'selected': False, 'addressDetail': 'xxxx', 'mobile': 'xxxx', 'idCard': '', 'phone': None, 'email': None, 'selfPickMobile': None, 'selfPickPhone': None, 'provinceName': None, 'cityName': None, 'countyName': None, 'townName': None, 'giftSenderConsigneeName': None, 'giftSenderConsigneeMobile': None, 'gcLat': 0.0, 'gcLng': 0.0, 'coord_type': 0, 'longitude': 0.0, 'latitude': 0.0, 'selfPickOptimize': 0, 'consigneeId': 0, 'selectedAddressType': 0, 'newCityName': None, 'newCountyName': None, 'newTownName': None, 'checkLevel': 0, 'optimizePickID': 0, 'pickType': 0, 'dataSign': 0, 'overseas': 0, 'areaCode': None, 'nameCode': None, 'appSelfPickAddress': 0, 'associatePickId': 0, 'associateAddressId': 0, 'appId': None, 'encryptText': None, 'certNum': None, 'addressType': 0, 'fullAddress': 'xxxx', 'postCode': None, 'addressDefault': False, 'addressName': None, 'selfPickAddressShuntFlag': 0, 'pickId': 0, 'pickName': None, 'pickVOselected': False, 'mapUrl': None, 'branchId': 0, 'canSelected': False, 'siteType': 0, 'helpMessage': None, 'tipInfo': None, 'cabinetAvailable': True, 'limitKeyword': 0, 'specialRemark': None, 'siteProvinceId': 0, 'siteCityId': 0, 'siteCountyId': 0, 'siteTownId': 0, 'skuSupported': False, 'addressSupported': 0, 'isCod': 0, 'consigneeName': None, 'pickVOname': None, 'shipmentType': 0, 'retTag': 0, 'tagSource': 0, 'userDefinedTag': None, 'newProvinceId': 0, 'newCityId': 0, 'newCountyId': 0, 'newTownId': 0, 'newProvinceName': None, 'used': False, 'address': None, 'name': 'xx', 'message': None, 'id': 0}, 'msgUuid': None, 'message': 'xxxxxx商品无货'}
                    # 下单成功
                    # {'overSea': False, 'orderXml': None, 'cartXml': None, 'noStockSkuIds': '', 'reqInfo': None, 'hasJxj': False, 'addedServiceList': None, 'sign': None, 'pin': 'xxx', 'needCheckCode': False, 'success': True, 'resultCode': 0, 'orderId': 8740xxxxx, 'submitSkuNum': 1, 'deductMoneyFlag': 0, 'goJumpOrderCenter': False, 'payInfo': None, 'scaleSkuInfoListVO': None, 'purchaseSkuInfoListVO': None, 'noSupportHomeServiceSkuList': None, 'msgMobile': None, 'addressVO': None, 'msgUuid': None, 'message': None}

                    if resp_json.get('success'):
                        order_id = resp_json.get('orderId')
                        logger.info('订单提交成功! 订单号：%s', order_id)
                        if self.send_message:
                            self.messenger.send(text='jd-assistant 订单提交成功', desp='订单号：%s' % order_id)
                        return True
                    else:
                        message, result_code = resp_json.get('message'), resp_json.get('resultCode')
                        if result_code == 0:
                            message = message + '(下单失败)'
                            # self._save_invoice()
                            # message = message + '(下单商品可能为第三方商品，将切换为普通发票进行尝试)'
                        elif result_code == 60077:
                            message = message + '(可能是购物车为空 或 未勾选购物车中商品)'
                        elif result_code == 60123:
                            message = message + '(需要在config.ini文件中配置支付密码)'
                        elif result_code == 600158:
                            logger.info('订单提交失败, 错误码：%s, 返回信息：%s', result_code, message)
                            logger.info(f'很抱歉，您抢购的商品无货！本次抢购结束')
                            return True
                        logger.info('订单提交失败, 错误码：%s, 返回信息：%s', result_code, message)
                        logger.info(f'响应数据：\n{resp_json}')
                        return False
                except Exception as e:
                    logger.error(e)
                    return False

        self.request_info['submit_order_request'] = submit_order_request

    def make_seckill_connect(self):
        # 获取商品抢购链接请求（多种，目前添加2种）
        self.socket_client.init_pool("itemko.jd.com", 443, 1, 20)
        self.socket_client.init_pool("item-soa.jd.com", 443, 1, 20)
        # 访问商品抢购链接请求
        self.socket_client.init_pool("yushou.jd.com", 443, 1, 10)
        # 访问抢购订单结算页面请求方法
        # 获取秒杀初始化信息请求
        self.socket_client.init_pool("marathon.jd.com", 443, 1, 10)
        # 【兼容】购物车请求
        self.socket_client.init_pool("cart.jd.com", 443, 1, 10)
        # 提交抢购（秒杀）订单请求
        self.socket_client.init_pool("trade.jd.com", 443, 1, 10)

    def make_reserve_seckill_connect(self):
        self.socket_client.init_pool("cart.jd.com", 443, 1)
        self.socket_client.init_pool("trade.jd.com", 443, 1, 15)

    def connect_now(self):
        self.socket_client.connect()

    def close_now(self):
        self.socket_client.close_client()

    def get_and_update_cookies_str(self):
        cookie_array = []
        for cookie in iter(self.sess.cookies):
            cookie_array.append(f'{cookie.name}={cookie.value};')
        self.cookies_str = ''.join(cookie_array)
        return self.cookies_str

    def get_cookies_str_by_domain_or_path(self, domain=None, path=None):
        cookie_array = []
        if domain is None:
            if path is None:
                for cookie in iter(self.sess.cookies):
                    cookie_array.append(f'{cookie.name}={cookie.value};')
            else:
                for cookie in iter(self.sess.cookies):
                    if cookie.path == path:
                        cookie_array.append(f'{cookie.name}={cookie.value};')
        elif path is None:
            if domain is None:
                for cookie in iter(self.sess.cookies):
                    cookie_array.append(f'{cookie.name}={cookie.value};')
            else:
                for cookie in iter(self.sess.cookies):
                    if cookie.domain in domain:
                        cookie_array.append(f'{cookie.name}={cookie.value};')
        else:
            for cookie in iter(self.sess.cookies):
                if (
                        (cookie.domain in domain) and
                        (cookie.path == path)
                ):
                    cookie_array.append(f'{cookie.name}={cookie.value};')
        return ''.join(cookie_array)

    def start_by_config(self, config=global_config):
        if config.select_mode == 1:
            # 执行【预约抢购，不会自动加入购物车】
            self.exec_seckill_by_time(config)
        elif config.select_mode == 2:
            # 执行【预约抢购，自动加入购物车】 手动清空自动添加到购物车的
            self.exec_reserve_seckill_by_time(config)
