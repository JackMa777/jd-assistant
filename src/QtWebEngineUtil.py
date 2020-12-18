import time
from inspect import isfunction

import lxml.html
from PyQt5.QtCore import *
from PyQt5.QtWebEngineWidgets import *
from PyQt5.QtWidgets import *
from PyQt5.QtNetwork import QNetworkCookie

from exception import AsstException


class CustomBrowser(QWebEngineView):
    # noinspection PyUnresolvedReferences
    def __init__(self, *args, **kwargs):
        self.app = QApplication([])
        QWebEngineView.__init__(self)
        self.html = ''
        self.tree: lxml.html.etree._Element = None
        # self.setProperty("--args", "--disable-web-security")
        # self.settings().setAttribute("--args --disable-web-security")

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
        profile = self.page().profile()
        cookie_store = profile.cookieStore()
        # QNetworkCookie.parseCookies(my_cookie_dict)
        for key, values in my_cookie_dict.items():
            jd_cookie = QNetworkCookie(name=QByteArray(key.encode()), value=QByteArray(values.encode()))
            # TODO 设置SameSite=None
            # jd_cookie.setHttpOnly(True)
            # jd_cookie.setDomain(headers['domian'])
            # jd_cookie.setSecure(True)
            # my_cookie.setName(key.encode())
            # my_cookie.setPath('/')
            # my_cookie.setValue(values.encode())
            cookie_store.setCookie(jd_cookie)
        # cookie_store.setProperty()
        cookie_store.loadAllCookies()
        profile.setHttpUserAgent(headers['User-Agent'])

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
            if jsStr and isfunction(jsCallback):
                def jsCallable(data):
                    jsCallback(data)
                self.page().runJavaScript(jsStr, jsCallable)

            def htmlCallable(data):
                self.html = data
                self.tree = lxml.html.fromstring(self.html)
                # dodo = self.page().action(QWebEnginePage.SelectAll)
            self.page().toHtml(htmlCallable)

            # self.show()
            self.quit()
        else:
            # 超时
            timer.stop()
            print('请求超时：' + self.url())
        self.app.exec_()

    def quit(self):
        self.app.quit()

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
