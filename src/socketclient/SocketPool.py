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

        self.conn_factory = conn_factory
        self.host = host
        self.port = port
        self.active_count = active_count
        self.max_count = max_count
        self.backend_mod = backend_mod

        self.pool = getattr(backend_mod, 'queue').Queue(max_count)

        for i in range(active_count):
            try:
                new_connect = conn_factory(host, port, backend_mod, True)
                if new_connect.is_connected():
                    self.pool.put_nowait(new_connect)
            except queue.Full:
                logger.error("队列已满")
                break
            except Exception as e:
                logger.error('新建连接异常，host：%s，port：%s，异常：%s', host, port, e)
        for i in range(max_count - active_count):
            try:
                new_connect = conn_factory(host, port, backend_mod)
                self.pool.put_nowait(new_connect)
            except queue.Full:
                logger.error("队列已满")
                break
            except Exception as e:
                logger.error('新建连接异常，host：%s，port：%s，异常：%s', host, port, e)

        self.max_lifetime = max_lifetime

        self.sem = self.backend_mod.Semaphore(1)

    def is_valid_connect(self, conn: Connector, _time=time.time()):
        if conn.is_connected():
            if conn.is_connecting():
                return self.max_lifetime > _time - conn.connect_time()
            else:
                return False
        return not conn.is_closed()

    def verify_connect(self, conn: Connector, _time=time.time()):
        if not conn:
            return False
        elif conn.host != self.host or conn.port != self.port:
            conn.invalidate()
            return False
        if self.is_valid_connect(conn, _time):
            return True
        else:
            conn.invalidate()
            return False

    def verify_all(self):
        current_pool_size = self.pool.qsize()
        if current_pool_size > 0:
            now = time.time()
            while True:
                try:
                    candidate = self.pool.get_nowait()
                    current_pool_size -= 1
                    if self.verify_connect(candidate, now):
                        self.pool.put_nowait(candidate)
                    if current_pool_size <= 0:
                        break
                except queue.Empty:
                    break
                except queue.Full:
                    break
                except Exception as e:
                    logger.error("异常信息：%s", e)

    @property
    def size(self):
        return self.pool.qsize()

    def invalidate_all(self):
        if self.pool.qsize():
            while True:
                try:
                    self.pool.get_nowait().invalidate()
                except queue.Empty:
                    break
                except Exception as e:
                    logger.error("异常信息：%s", e)
        logger.info("主机[%s]端口[%s]所有连接释放完成", self.host, self.port)

    def put_connect(self, conn: Connector):
        with self.sem:
            if self.pool.qsize() < self.max_count:
                if self.verify_connect(conn):
                    try:
                        self.pool.put_nowait(conn)
                    except queue.Full:
                        conn.invalidate()
            else:
                conn.invalidate()

    def get_connect(self, host=None, port=80):
        found = None
        i = self.pool.qsize()
        if i:
            now = time.time()
            while True:
                try:
                    i -= 1
                    candidate = self.pool.get_nowait()
                    if self.verify_connect(candidate, now):
                        found = candidate
                        break
                    if i <= 0:
                        break
                except queue.Empty:
                    return None
                except Exception as e:
                    logger.error("异常信息：%s", e)

        # we got one.. we use it
        if found is not None:
            return found

        try:
            new_item = self.conn_factory(host, port, self.backend_mod)
        except Exception as e:
            logger.error("创建连接异常，信息：%s", e)
        else:
            # we should be connected now
            new_item.connect()
            with self.sem:
                return new_item

    def connect_all(self):
        qsize = self.pool.qsize()
        if qsize:
            while True:
                try:
                    qsize -= 1
                    conn = self.pool.get_nowait()
                    if self.is_valid_connect(conn):
                        conn.connect()
                        self.pool.put_nowait(conn)
                    else:
                        conn.invalidate()
                    if qsize <= 0:
                        break
                except queue.Full:
                    break
                except queue.Empty:
                    break
                except Exception as e:
                    logger.error("异常信息：%s", e)
        for i in range(self.max_count - self.pool.qsize()):
            try:
                new_connect = self.conn_factory(self.host, self.port, self.backend_mod)
                self.pool.put_nowait(new_connect)
            except queue.Full:
                break
            except Exception as e:
                logger.error('新建连接异常：%s', e)
        logger.info("与主机[%s]端口[%s]成功建立[%s]个连接", self.host, self.port, self.pool.qsize())
