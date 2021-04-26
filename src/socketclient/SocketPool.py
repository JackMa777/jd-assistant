# -*- coding: utf-8 -
#
# This file is part of socketpool.
# See the NOTICE for more information.

import time

from log import logger
from socketclient import Connector


class MaxTriesError(Exception):
    pass


class MaxConnectionsError(Exception):
    pass


class SocketPool(object):
    """Pool of socket connections"""

    def __init__(self, factory, host=None, port=80, active_count=3, max_count=10,
                 backend_mod=None,
                 max_lifetime=600.):

        self.factory = factory
        self.host = host
        self.port = port
        self.active_count = active_count
        self.max_count = max_count
        self.backend_mod = backend_mod

        self.pool = getattr(backend_mod, 'queue').LifoQueue()

        for i in range(max_count - active_count):
            try:
                new_connect = factory(host, port, backend_mod)
                self.pool.put(new_connect)
            except Exception as e:
                logger.error('新建连接异常，host：%s，port：%s，异常：%s', host, port, e)
        for i in range(active_count):
            try:
                new_connect = factory(host, port, backend_mod, True)
                if new_connect.is_connected():
                    self.pool.put(new_connect)
            except Exception as e:
                logger.error('新建连接异常，host：%s，port：%s，异常：%s', host, port, e)

        self._free_conns = 0
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
            for candidate in self.pool:
                current_pool_size -= 1
                if self.verify_connect(candidate, now):
                    self.pool.put(candidate)
                if current_pool_size <= 0:
                    break

    @property
    def size(self):
        return self.pool.qsize()

    def release_all(self):
        if self.pool.qsize():
            for conn in self.pool:
                conn.invalidate()

    def put_connect(self, conn: Connector):
        with self.sem:
            if self.pool.qsize() < self.max_count:
                if self.verify_connect(conn):
                    self.pool.put(conn)
            else:
                conn.invalidate()

    def release_connection(self, conn):
        self.put_connect(conn)

    def get_queue(self, host, port):
        pass

    def get_connect(self, host=None, port=80):

        found = None
        i = self.pool.qsize()
        last_error = None

        if self.pool.qsize():
            now = time.time()
            while True:
                candidate = self.pool.get()
                i -= 1
                if self.verify_connect(candidate, now):
                    found = candidate
                    break

                if i <= 0:
                    break

        # we got one.. we use it
        if found is not None:
            return found

        try:
            new_item = self.factory(host, port)
        except Exception as e:
            last_error = e
        else:
            # we should be connected now
            new_item.connect()
            with self.sem:
                return new_item

        if last_error is None:
            raise MaxTriesError()
        else:
            raise last_error
