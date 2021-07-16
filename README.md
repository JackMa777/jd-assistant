# 魔改JD-Assistant

[![version](https://img.shields.io/badge/python-3.4+-blue.svg)](https://www.python.org/download/releases/3.4.0/) 
[![status](https://img.shields.io/badge/status-stable-green.svg)](https://github.com/tychxn/jd-assistant)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![star, issue](https://img.shields.io/badge/star%2C%20issue-welcome-brightgreen.svg)](https://github.com/tychxn/jd-assistant)

#### http请求客户端使用自己定制的SocketClient（内部维护连接池，抢购前建立连接）
#### 抢购调用接口未修改，都是原作者提供，可能已失效，不确保可用
#### 支持并发

##### 该项目仅供学习参考

## 运行环境

- [Python 3](https://www.python.org/)

## 第三方库

- [Requests](http://docs.python-requests.org/en/master/)
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- [PyCryptodome](https://github.com/Legrandin/pycryptodome)
- 等

#### 部分代码参考
- [SocketPool](https://github.com/benoitc/socketpool)

windows下安装：
```sh
pip install -r requirements_windows.txt
```

linux下安装：
```sh
pip install -r requirements_linux.txt
```

## 使用教程

程序主入口在 `main.py`

👉 [使用教程请参看Wiki](https://github.com/tychxn/jd-assistant/wiki/1.-%E4%BA%AC%E4%B8%9C%E6%8A%A2%E8%B4%AD%E5%8A%A9%E6%89%8B%E7%94%A8%E6%B3%95)