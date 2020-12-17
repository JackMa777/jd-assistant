import time
from inspect import isfunction

import lxml.html
from PyQt5.QtCore import *
from PyQt5.QtWebEngineWidgets import *
from PyQt5.QtWidgets import *
from PyQt5.QtNetwork import QNetworkCookieJar, QNetworkCookie

from exception import AsstException


class CustomBrowser(QWebEngineView):
    # noinspection PyUnresolvedReferences
    def __init__(self, *args, **kwargs):
        self.app = QApplication([])
        QWebEngineView.__init__(self)
        self.cookie_jar = QNetworkCookieJar()
        self.html = ''
        self.tree: lxml.html.etree._Element = None

    def open(self, url, headers=None, jsStr=None, jsCallback=None, timeout=10):
        def loadUrl():
            self.setHeaders(headers)
            return self.load(QUrl(url))

        self.customizeOpenPage(loadUrl, jsStr, jsCallback, timeout)

    def openLocalPage(self, htmlPath, headers=None, jsStr=None, jsCallback=None, timeout=10):
        def loadHtml():
            self.setHeaders(headers)
            with open(htmlPath, 'r', encoding='utf8') as f:
                html = f.read()
                self.setHtml(html)

        self.customizeOpenPage(loadHtml, jsStr, jsCallback, timeout)

    def setHeaders(self, headers):
        my_cookie_dict = headers['cookies']
        # cookies = []
        page = self.page()
        cookie_store = page.cookieStore()
        for key, values in my_cookie_dict.items():
            my_cookie = QNetworkCookie(name=QByteArray(key.encode()), value=QByteArray(values.encode()))
            # my_cookie.setName(key.encode())
            my_cookie.setDomain(headers['origin'])
            my_cookie.setPath(headers['origin'])
            # my_cookie.setValue(values.encode())
            cookie_store.cookieAdded(my_cookie)
            # my_cookie = QNetworkCookie(name=QByteArray(key), value=QByteArray(values))
            # cookies.append(my_cookie)

        # self.cookie_jar.setAllCookies(cookies)

        # self.cookie_jar.setCookiesFromUrl(cookies, QUrl('https://www.baidu.com/'))

        # page.profile().cookieStore().setCookie(my_cookie)

        # page.profile().cookieStore().setCookie(self.cookie_jar)

        page.profile().setHttpUserAgent(headers['User-Agent'])

    def customizeOpenPage(self, loadFunc, jsStr=None, jsCallback=None, timeout=10):
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
        loop.exec_()  # 开始执行，并等待加载完成
        if timer.isActive():
            # 加载完成执行
            timer.stop()

            def htmlCallable(data):
                self.html = data
                self.tree = lxml.html.fromstring(self.html)
                # dodo = self.page().action(QWebEnginePage.SelectAll)
            self.page().toHtml(htmlCallable)
            if jsStr and isfunction(jsCallback):
                def jsCallable(data):
                    jsCallback(data)
                    self.app.quit()
                self.page().runJavaScript(jsStr, jsCallable)
        else:
            # 超时
            timer.stop()
            print('请求超时：' + self.url())
        self.app.exec_()

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
