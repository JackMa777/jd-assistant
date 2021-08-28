import os
from http.cookiejar import CookieJar
from inspect import isfunction

from selenium import webdriver

from log import logger


class CustomBrowser(object):

    def __init__(self, user_agent, chromedriver_path=None, chrome_path=None, headless=True):

        chrome_options = webdriver.ChromeOptions()
        chrome_options.headless = headless
        chrome_options.add_argument('--no-sandbox')
        # chrome_options.add_argument('--no-proxy-server')
        # chrome_options.add_argument('--proxy-server=127.0.0.1:8080')
        # chrome_options.add_argument('--proxy-pac-url')
        chrome_options.add_argument(f'user-agent="{user_agent}"')
        chrome_options.add_argument(f'--user-data-dir={os.path.dirname(os.getcwd())}/Browser/Data')
        chrome_options.add_argument(f'-–disk-cache-dir={os.path.dirname(os.getcwd())}/Browser/Cache')
        chrome_options.add_experimental_option("excludeSwitches", ['enable-automation', 'enable-logging'])
        if chrome_path:
            chrome_options.binary_location = chrome_path
        count = 0
        client = None
        while True:
            try:
                if chromedriver_path:
                    self.client = webdriver.Chrome(executable_path=chromedriver_path, chrome_options=chrome_options)
                else:
                    self.client = webdriver.Chrome(chrome_options=chrome_options)
                client = self.client
            # try:
            # client.delete_all_cookies()
            except Exception as e:
                count += 1
                if client:
                    client.quit()
                logger.error(e)
                logger.error(f'无法初始化浏览器，请检查config.ini文件中chromedriver_path与chrome_path的配置 或 检查网络代理是否关闭，开启代理会导致浏览器初始化失败')
                logger.info(
                    'chromedriver可在 http://npm.taobao.org/mirrors/chromedriver/ '
                    '下载，注意下载与chrome对应的版本，复制文件路径到chromedriver_path即可')
                logger.info('chrome需自行下载，安装版无需配置，精简版复制chrome可执行文件路径到chrome_path即可')
                if count > 3:
                    raise e
                continue
            else:
                break

    def set_cookies(self, cookies: CookieJar, domain):
        if cookies:
            for cookie in iter(cookies):
                if cookie.domain in domain:
                    cookie_dict = {
                        'name': cookie.name,
                        'value': cookie.value,
                        'path': cookie.path,
                        'domain': cookie.domain,
                        'secure': cookie.secure
                    }
                    if cookie.expires:
                        cookie_dict['expiry'] = cookie.expires
                    self.client.add_cookie(cookie_dict)

    def close(self):
        self.client.close()

    def openUrl(self, url, jsScript=None, timeout=5):
        client = self.client
        client.set_script_timeout(timeout)
        client.get(url)
        if jsScript:
            js_str = jsScript.js_str
            if js_str:
                js_data = client.execute_script(js_str)
                js_callback = jsScript.js_callback
                if isfunction(js_callback):
                    return js_callback(js_data)
        return client.page_source

    def quit(self):
        self.client.quit()


class JsScript:

    def __init__(self, js_str, js_callback):
        self.js_str = js_str
        self.js_callback = js_callback
