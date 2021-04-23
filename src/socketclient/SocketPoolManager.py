# -*- coding: utf-8 -
#
# This file is part of socketpool.
# See the NOTICE for more information.

from urllib3._collections import RecentlyUsedContainer

from socketclient import Connector
from socketclient.SocketPool import SocketPool
from socketpool.util import load_backend


class MaxTriesError(Exception):
    pass


class MaxConnectionsError(Exception):
    pass


class CustomRecentlyUsedContainer(RecentlyUsedContainer):
    def __iter__(self):
        raise NotImplementedError(
            "Iteration over this class is unlikely to be threadsafe."
        )

    def get(self, key):
        return self._container[key]


class SocketPoolManager(object):
    """Pool of connections

    This is the main object to maintain connection. Connections are
    created using the factory instance passed as an option.

    Options:
    --------

    :attr factory: Instance of socketpool.Connector. See
        socketpool.conn.TcpConnector for an example
    :attr retry_max: int, default 3. Numbr of times to retry a
        connection before raising the MaxTriesError exception.
    :attr max_lifetime: int, default 600. time in ms we keep a
        connection in the pool
    :attr max_size: int, default 10. Maximum number of connections we
        keep in the pool.
    :attr options: Options to pass to the factory
    :attr reap_connection: boolean, default is true. If true a process
        will be launched in background to kill idle connections.
    :attr backend: string, default is thread. The socket pool can use
        different backend to handle process and connections. For now
        the backends "thread", "gevent" and "eventlet" are supported. But
        you can add your own backend if you want. For an example of backend,
        look at the module socketpool.gevent_backend.
    """

    def __init__(self, factory,
                 retry_max=3, retry_delay=.1,
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
        self._free_conns = 0
        self.factory = factory
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

    def get_pool(self, host=None, port=80, init=True):
        # TODO
        pool = self.pools[(host, port)]
        if not pool:
            if init is True:
                pool = self.init_pool(host, port)
            else:
                with self.sem:
                    if self.pools.__len__() < self.max_pool:
                        pool = self.init_pool(host, port)
        return pool

    def init_pool(self, host=None, port=80, active_count=3, max_count=10):
        with self.sem:
            pool = SocketPool(self.factory, host, port, active_count, max_count, self.backend_mod)
            # TODO
            self.pools[(host, port)] = pool
        return pool

    # def stop_reaper(self):
    #     self._reaper.forceStop = True
    #
    # def __del__(self):
    #     self.stop_reaper()

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
            return pool.get_connect(host, port)
        else:
            return None
