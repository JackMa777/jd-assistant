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

    def __init__(self, conn_factory,
                 retry_max=3, retry_delay=.01,
                 timeout=-1, max_lifetime=600.,
                 max_pool=10, options=None,
                 reap_connections=True, reap_delay=1,
                 backend="thread"):

        if isinstance(backend, str):
            self.backend_mod = load_backend(backend)
            self.backend = backend
        else:
            self.backend_mod = backend
            self.backend = str(getattr(backend, '__name__', backend))
        self.max_pool = max_pool
        self.pools = CustomRecentlyUsedContainer(max_pool, dispose_func=lambda p: p.release_all())
        self.conn_factory = conn_factory
        self.retry_max = retry_max
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.max_lifetime = max_lifetime
        if options is None:
            self.options = {"backend_mod": self.backend_mod}
        else:
            self.options = options
            self.options["backend_mod"] = self.backend_mod

        self.sem = self.backend_mod.Semaphore(1)

        self._reaper = None
        if reap_connections:
            self.reap_delay = reap_delay
            self.start_reaper()

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

    def init_pool(self, host=None, port=80, active_count=3, max_count=10):
        with self.sem:
            pool = SocketPool(self.conn_factory, host, port, active_count, max_count, self.backend_mod)
            self.pools[(host, port)] = pool
        return pool

    def verify_pool(self):
        for key in self.pools.keys():
            pool = self.pools.get(key)
            if pool:
                with self.sem:
                    if pool.size() <= 0:
                        del self.pools[key]
                    else:
                        pool.verify_all()

    def keep_pool(self):
        # TODO 需要根据active_count进行异步保活
        pass

    def start_reaper(self):
        pass
        # TODO
        # self._reaper = self.backend_mod.ConnectionReaper(self,
        #                                                  delay=self.reap_delay)
        # self._reaper.ensure_started()

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

    def get_connect(self, host=None, port=80):
        pool = self.get_pool(host, port)
        if pool:
            tries = 0
            while tries < self.retry_max:
                try:
                    conn = pool.get_connect(host, port)
                    if conn:
                        return conn
                except Exception as e:
                    logger.error('获取连接异常，重试第：%s次，异常：%s', tries, e)
                tries += 1
                self.backend_mod.sleep(self.retry_delay)
        return None
