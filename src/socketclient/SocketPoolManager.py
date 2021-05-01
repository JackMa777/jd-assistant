# -*- coding: utf-8 -
import logging

from urllib3._collections import RecentlyUsedContainer

from socketclient import Connector
from socketclient.SocketPool import SocketPool
from socketclient.util import load_backend

logger = logging.getLogger()


class CustomRecentlyUsedContainer(RecentlyUsedContainer):
    def __iter__(self):
        super(CustomRecentlyUsedContainer, self).__iter__()

    def get(self, key):
        if key in self._container:
            return self._container[key]
        return None


class SocketPoolManager(object):
    """Pool of socket manager"""

    def __init__(self, conn_factory, backend_mod=None, max_pool=10,
                 verify_interval_time=0):
        self.max_pool = max_pool
        self.pools = CustomRecentlyUsedContainer(max_pool, dispose_func=lambda p: p.invalidate_all())
        self.conn_factory = conn_factory
        if not backend_mod:
            backend_mod = load_backend("thread")
        self.backend_mod = backend_mod
        self.sem = self.backend_mod.Semaphore(1)

        self._reaper = None
        if verify_interval_time > 0:
            self.verify_interval_time = verify_interval_time
            self.start_verifying()

    @property
    def size(self):
        return self.pools.__len__()

    def clear_pools(self):
        self.pools.clear()

    def get_pool(self, host=None, port=80, full_init=True):
        pool = self.pools.get((host, port))
        if not pool:
            if full_init is True:
                pool = self.init_pool(host, port)
            else:
                with self.sem:
                    if self.pools.__len__() < self.max_pool:
                        pool = self.init_pool(host, port)
        return pool

    def init_pool(self, host=None, port=80, active_count=3, max_count=10, life_time=50):
        with self.sem:
            pool = SocketPool(self.conn_factory, host, port, active_count, max_count, life_time, self.backend_mod)
            self.pools[(host, port)] = pool
        return pool

    def verify_pools(self):
        for key in self.pools.keys():
            pool = self.pools.get(key)
            if pool:
                with self.sem:
                    if pool.size() <= 0:
                        del self.pools[key]
                    else:
                        pool.verify_all()

    def start_verifying(self):
        pass
        # TODO 启动新线程/协程 轮询保活方法
        # self.verify_pools
        # self._reaper = self.backend_mod.ConnectionReaper(self,
        #                                                  delay=self.reap_delay)

    def release_connection(self, conn):
        if self._reaper is not None:
            self._reaper.ensure_started()

        self.put_connect(conn)

    def put_connect(self, conn: Connector):
        pool = self.get_pool(conn.host, conn.port, False)
        if pool:
            pool.put_connect(conn)
        else:
            # 释放该连接
            conn.invalidate()

    def connect_all(self):
        with self.sem:
            for key in self.pools.keys():
                pool = self.pools.get(key)
                if pool:
                    pool.connect_all()
