import time
from inspect import isfunction

import lxml.html
from PyQt5.QtCore import *
from PyQt5.QtNetwork import QNetworkCookie
from PyQt5.QtWebEngineCore import QWebEngineHttpRequest
from PyQt5.QtWebEngineWidgets import *
from PyQt5.QtWidgets import *

from exception import AsstException


class CustomBrowser(QWebEngineView):

    def __init__(self, cookies, user_agent, *args, **kwargs):
        self.app = QApplication([])
        QWebEngineView.__init__(self)
        self.html = ''
        self.tree: lxml.html.etree._Element = None
        page = self.page()
        profile = page.profile().defaultProfile()
        self.showMinimized()
        # TODO 指定缓存路径
        # profile.setCachePath('./qt/Cache')
        # profile.setPersistentStoragePath('./qt/WebEngine')
        # settings = self.settings()
        # page.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        # page.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        # 本地存储必须开启
        self.settings().setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        my_cookie_dict = cookies
        if user_agent:
            profile.setHttpUserAgent(user_agent)
        cookie_store = profile.cookieStore()
        # cookie_store.deleteAllCookies()
        for cookie in iter(my_cookie_dict):
            jd_cookie = QNetworkCookie(name=QByteArray(cookie.name.encode()), value=QByteArray(cookie.value.encode()))
            # jd_cookie.setHttpOnly(True)
            # jd_cookie.setExpirationDate(cookie.expires)
            jd_cookie.setSecure(cookie.secure)
            jd_cookie.setPath(cookie.path)
            jd_cookie.setDomain(cookie.domain)
            cookie_store.setCookie(jd_cookie)
        cookie_store.loadAllCookies()

    def openGetUrl(self, url, headers=None, JsScript=None, timeout=10):
        if headers is None:
            headers = dict()

        def loadUrl():
            request = QWebEngineHttpRequest()
            request.setUrl(QUrl(url))
            request.setMethod(QWebEngineHttpRequest.Method.Get)
            for key, values in headers.items():
                request.setHeader(QByteArray(key.encode()), QByteArray(values.encode()))
            self.load(request)

        self.customizeOpenPage(loadUrl, JsScript, timeout)

    def customizeOpenPage(self, loadFunc, JsScript=None, timeout=30):
        if not loadFunc:
            raise AsstException('加载方法为空')
        loop = QEventLoop()
        # timer = QTimer.singleShot(timeout * 1000, loop.quit)
        """添加超时等待页面加载完成"""
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        self.loadFinished.connect(loop.quit)
        loadFunc()
        timer.start(timeout * 1000)
        # self.show()
        loop.exec_()  # 开始执行，并等待加载完成
        if timer.isActive():
            # 加载完成执行
            timer.stop()
            if JsScript:
                js_str = JsScript.js_str
                js_callback = JsScript.js_callback
                if js_str and isfunction(js_callback):
                    def jsCallAble(data):
                        js_callback(data)
                    time.sleep(2)
                    self.page().runJavaScript(js_str, jsCallAble)

            def htmlCallable(data):
                self.html = data
                self.tree = lxml.html.fromstring(self.html)
                self.app.quit()
                # dodo = self.page().action(QWebEnginePage.SelectAll)

            self.page().toHtml(htmlCallable)
        else:
            # 超时
            timer.stop()
            print('页面请求超时')
        self.app.exec_()

    def quit(self):
        self.app.quit()
        self.destroy()

    def get_html(self):
        """Shortcut to return the current HTML"""
        return self.html

    def find(self, pattern):
        """Find all elements that match the pattern"""
        # return self.page().mainFrame().findAllElements(pattern)
        return self.tree.cssselect(pattern)

    def attr(self, pattern, name, value):
        """Set attribute for matching elements"""
        for e in self.find(pattern):
            e.attrib.update({name: value})

        # self.page().setHtml(str(lxml.html.tostring(self.tree), encoding="utf8"), baseUrl=QUrl('http://example.python-scraping.com/search'))
        # self.setHtml(str(lxml.html.tostring(self.tree), encoding="utf8"))

    def text(self, pattern, value):
        """Set attribute for matching elements"""
        for e in self.find(pattern):
            e.text = value

        # self.page().setHtml(str(lxml.html.tostring(self.tree), encoding="utf8"), baseUrl=QUrl('http://example.python-scraping.com/search'))
        # self.setHtml(str(lxml.html.tostring(self.tree), encoding="utf8"))

    def setSearchItem(self, pattern, search_value):
        """Click matching elements"""
        page: QWebEnginePage = self.page()
        js_string = '''
        function myFunction(id, value)
        {{
            document.getElementById(id).value = value;
            document.getElementById('page_size').children[1].selected = true
            document.getElementById('page_size').children[1].innerText = 1000
            return document.getElementById(id).value;
        }}

        myFunction("{id}", "{value}");
        '''

        for e in self.find(pattern):
            page.runJavaScript(js_string.format(id=e.attrib['id'], value=search_value), self.js_callback)

        self.app.exec_()

    def click(self, pattern):
        """Click matching elements"""
        page: QWebEnginePage = self.page()
        js_string = '''
        function myFunction(id)
        {{
            document.getElementById(id).click();
            return id
        }}

        myFunction("{id}");
        '''

        for e in self.find(pattern):
            page.runJavaScript(js_string.format(id=e.attrib['id']), self.js_callback)

        self.app.exec_()

    def js_callback(self, result):
        print(result)
        self.app.quit()
        # QMessageBox.information(self, "提示", str(result))

    def wait_load(self, pattern, timeout=60):
        """Wait for this pattern to be found in webpage and return matches"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.app.processEvents()

            matches = self.find(pattern)
            if matches:
                return matches
            else:
                self.page().toHtml(self.callable)
                self.app.exec_()
        print('Wait load timed out')


class JsScript:

    def __init__(self, js_str, js_callback):
        self.js_str = js_str
        self.js_callback = js_callback
