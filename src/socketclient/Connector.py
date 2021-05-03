# -*- coding: utf-8 -
import logging
import socket
import ssl
import time

from socketclient import util

logger = logging.getLogger()


class Connector(object):

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self._connected = False
        self._closed = False
        self._connect_time = None

    def is_match(self, match_host=None, match_port=None):
        return match_host == self.host and match_port == self.port

    def connect(self):
        self._connect_time = time.time()
        raise NotImplementedError()

    def is_valid_connect(self):
        raise NotImplementedError()

    def keep_connect(self):
        raise NotImplementedError()

    def send(self, data):
        raise NotImplementedError()

    def do_func(self, func, **params):
        raise NotImplementedError()

    def is_connected(self):
        return self._connected

    def is_closed(self):
        return self._closed

    def connect_time(self):
        return self._connect_time

    def handle_exception(self, exception):
        raise NotImplementedError()

    def invalidate(self):
        raise NotImplementedError()


class TcpConnector(Connector):
    HTTP = 80
    HTTPS = 443

    def __init__(self, host, port, backend_mod, is_connect=False, timeout=0.5):
        super().__init__(host, port)
        sock = backend_mod.Socket(socket.AF_INET, socket.SOCK_STREAM)
        # 禁用Nagle算法
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # TODO 保活未生效
        # 开启保活
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # 第一次探测时间，单位：秒
        sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPIDLE, 30)
        # 第二次及以后探测时间，单位：秒
        sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPINTVL, 30)
        # 失败重试次数
        sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPCNT, 5)
        sock.setblocking(True)
        sock.settimeout(timeout)
        if port == TcpConnector.HTTP:
            pass
        elif port == TcpConnector.HTTPS:
            sock = ssl.wrap_socket(sock)
        else:
            raise Exception("端口错误")
        self._s = sock
        if is_connect:
            self.connect()
        self.backend_mod = backend_mod
        # self._s_file = self._s.makefile(mode, bufsize)

    def connect(self):
        if self._connected:
            return
        if self._closed:
            raise Exception("连接已关闭")
        self._s.connect((self.host, self.port))
        self._connected = True
        self._connect_time = time.time()

    def keep_connect(self, _time=time.time()):
        # TODO 保活
        # self._connect_time = _time
        # print(self._s.send(bytes(0xFF)))
        pass

    def send(self, *args):
        self.connect()
        return self._s.sendall(*args)

    def do_func(self, func, **params):
        if func:
            return func(self._s, **params)
        return None

    def is_connected(self):
        return self._connected

    def is_connecting(self):
        return util.is_connected(self._s)

    def is_closed(self):
        return self._closed or self._s._closed

    def handle_exception(self, exception):
        logger.error('异常：%s', exception)

    def invalidate(self):
        if not self._closed:
            self._s.close()
            # self._s_file.close()
            self._closed = True

    # def __del__(self):
    #     self.invalidate()

    # def read(self, size=-1):
    #     return self._s_file.read(size)

    # def readline(self, size=-1):
    #     return self._s_file.readline(size)

    # def readlines(self, sizehint=0):
    #     return self._s_file.readlines(sizehint)

    def recv(self, size=1024):
        return self._s.recv(size)
