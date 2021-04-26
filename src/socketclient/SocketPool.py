# -*- coding: utf-8 -
import queue
import time

from log import logger
from socketclient import Connector


class SocketPool(object):
    """Pool of socket connections"""

    def __init__(self, conn_factory, host=None, port=80, active_count=3, max_count=10,
                 backend_mod=None,
                 max_lifetime=600.):

        self.factory = conn_factory
        self.host = host
        self.port = port
        self.active_count = active_count
        self.max_count = max_count
        self.backend_mod = backend_mod

        self.pool = getattr(backend_mod, 'queue').LifoQueue()

        for i in range(max_count - active_count):
            try:
                new_connect = conn_factory(host, port, backend_mod)
                self.pool.put(new_connect)
            except Exception as e:
                logger.error('新建连接异常，host：%s，port：%s，异常：%s', host, port, e)
        for i in range(active_count):
            try:
                new_connect = conn_factory(host, port, backend_mod, True)
                if new_connect.is_connected():
                    self.pool.put(new_connect)
            except Exception as e:
                logger.error('新建连接异常，host：%s，port：%s，异常：%s', host, port, e)

        self.max_lifetime = max_lifetime

        self.sem = self.backend_mod.Semaphore(1)

    def is_valid_connect(self, conn: Connector, _time=time.time()):
        if conn.is_connected():
            return self.max_lifetime > _time - conn.connect_time()
        return not conn.is_closed()

    def verify_connect(self, conn: Connector, _time=time.time()):
        if not conn:
            return False
        elif conn.host != self.host or conn.port != self.port:
            conn.invalidate()
            return False
        elif conn.is_connected():
            if conn.connect_time() + self.max_lifetime < _time:
                conn.invalidate()
                return False
        elif conn.is_closed():
            conn.invalidate()
            return False
        return True

    def verify_all(self):
        current_pool_size = self.pool.qsize()
        if current_pool_size > 0:
            now = time.time()
            while True:
                try:
                    candidate = self.pool.get_nowait()
                    current_pool_size -= 1
                    if self.verify_connect(candidate, now):
                        self.pool.put(candidate)
                    if current_pool_size <= 0:
                        break
                except queue.Empty:
                    break

    @property
    def size(self):
        return self.pool.qsize()

    def release_all(self):
        if self.pool.qsize():
            while True:
                try:
                    self.pool.get_nowait().invalidate()
                except queue.Empty:
                    break
        logger.info("主机[%s]端口[%s]所有连接释放完成", self.host, self.port)

    def put_connect(self, conn: Connector):
        with self.sem:
            if self.pool.qsize() < self.max_count:
                if self.verify_connect(conn):
                    self.pool.put(conn)
            else:
                conn.invalidate()

    def get_connect(self, host=None, port=80):
        found = None
        i = self.pool.qsize()
        if i:
            now = time.time()
            while True:
                try:
                    candidate = self.pool.get_nowait()
                    i -= 1
                    if self.verify_connect(candidate, now):
                        found = candidate
                        break
                    if i <= 0:
                        break
                except queue.Empty:
                    return None

        # we got one.. we use it
        if found is not None:
            return found

        try:
            new_item = self.factory(host, port)
        except Exception as e:
            logger.error("创建连接异常，信息：%s", e)
        else:
            # we should be connected now
            new_item.connect()
            with self.sem:
                return new_item
