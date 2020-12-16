import time
from inspect import isfunction

import lxml.html
from PyQt5.QtCore import *
from PyQt5.QtWebEngineWidgets import *
from PyQt5.QtWidgets import *


class CustomBrowser(QWebEngineView):
    # noinspection PyUnresolvedReferences
    def __init__(self, *args, **kwargs):
        self.app = QApplication([])
        QWebEngineView.__init__(self)
        self.html = ''
        self.tree: lxml.html.etree._Element = None

    def open(self, url, jsStr=None, jsCallback=None, timeout=10):
        loop = QEventLoop()
        # timer = QTimer.singleShot(timeout * 1000, loop.quit)
        """添加超时等待页面加载完成"""
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        self.loadFinished.connect(loop.quit)
        self.load(QUrl(url))
        timer.start(timeout * 1000)
        loop.exec_()  # 开始执行，并等待加载完成
        if timer.isActive():
            # 加载完成执行
            timer.stop()
            self.page().toHtml(self.htmlCallable)
            if jsStr and isfunction(jsCallback):
                def jsCallable(data):
                    jsCallback(data)
                    self.app.quit()

                self.page().runJavaScript(jsStr, jsCallable)
        else:
            # 超时
            timer.stop()
            print('请求超时：' + url)

        self.app.exec_()

    def openLocalPage(self, path):
        with open(path, 'r') as f:
            html = f.read()
            self.webEngineView.setHtml(html)

    def htmlCallable(self, data):
        self.html = data
        self.tree = lxml.html.fromstring(self.html)
        # dodo = self.page().action(QWebEnginePage.SelectAll)

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
