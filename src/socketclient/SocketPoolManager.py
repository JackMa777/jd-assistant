# -*- coding: utf-8 -
#
# This file is part of socketpool.
# See the NOTICE for more information.

import contextlib
import time

from urllib3._collections import RecentlyUsedContainer

from log import logger
from socketclient import Connector
from socketclient.SocketPool import SocketPool
from socketpool.util import load_backend


class MaxTriesError(Exception):
    pass


class MaxConnectionsError(Exception):
    pass


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
        self.pool = None
        self.pools = RecentlyUsedContainer(max_pool, dispose_func=lambda p: p.release_all())
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

        self.lock = self.backend_mod.RLock()

        self._reaper = None
        if reap_connections:
            self.reap_delay = reap_delay
            self.start_reaper()

    @property
    def size(self):
        return self.pool.qsize()

    def get_pool(self, host=None, port=80, init=True):
        pool = self.pools[(host, port)]
        if not pool:
            if init is True:
                pool = self.init_pool(host, port)
            else:
                with self.lock:
                    if self.pools.__len__() < self.max_pool:
                        pool = self.init_pool(host, port)
        return pool

    def init_pool(self, host=None, port=80, active_count=3, max_count=10):
        with self.lock:
            pool = SocketPool(self.factory, host, port, active_count, max_count, self.backend_mod)
            self.pools[(host, port)] = pool
        return pool

    def stop_reaper(self):
        self._reaper.forceStop = True

    def __del__(self):
        self.stop_reaper()

    def murder_connections(self):
        current_pool_size = self.pool.qsize()
        if current_pool_size > 0:
            for priority, candidate in self.pool:
                current_pool_size -= 1
                if not self.too_old(candidate):
                    self.pool.put((priority, candidate))
                else:
                    self._reap_connection(candidate)
                if current_pool_size <= 0:
                    break

    def start_reaper(self):
        self._reaper = self.backend_mod.ConnectionReaper(self,
                                                         delay=self.reap_delay)
        self._reaper.ensure_started()

    def release_connection(self, conn):
        if self._reaper is not None:
            self._reaper.ensure_started()

        self.set_connect(conn)

    def set_connect(self, conn: Connector):
        pool = self.get_pool(conn.host, conn.port, False)
        if pool:
            pool.put_connect(conn)
        else:
            # 释放该连接
            if conn.is_connected():
                conn.invalidate()

    def get_connect(self, **options):
        options.update(self.options)
        # Do not set this in self.options so we don't keep a persistent
        # reference on the pool which would prevent garbage collection.
        options["pool"] = self

        found = None
        i = self.pool.qsize()
        tries = 0
        last_error = None

        unmatched = []

        while tries < self.retry_max:
            # first let's try to find a matching one from pool

            if self.pool.qsize():
                for priority, candidate in self.pool:
                    i -= 1
                    if self.too_old(candidate):
                        # let's drop it
                        self._reap_connection(candidate)
                        continue

                    matches = candidate.matches(**options)
                    if not matches:
                        # let's put it back
                        unmatched.append((priority, candidate))
                    else:
                        if candidate.is_connected():
                            found = candidate
                            break
                        else:
                            # conn is dead for some reason.
                            # reap it.
                            self._reap_connection(candidate)

                    if i <= 0:
                        break

            if unmatched:
                for candidate in unmatched:
                    self.pool.put(candidate)

            # we got one.. we use it
            if found is not None:
                return found

            try:
                new_item = self.factory(**options)
            except Exception as e:
                last_error = e
            else:
                # we should be connected now
                if new_item.is_connected():
                    with self.lock:
                        return new_item

            tries += 1
            self.backend_mod.sleep(self.retry_delay)

        if last_error is None:
            raise MaxTriesError()
        else:
            raise last_error

    @contextlib.contextmanager
    def connection(self, **options):
        conn = self.get_connect(**options)
        try:
            yield conn
            # what to do in case of success
        except Exception as e:
            conn.handle_exception(e)
        finally:
            self.release_connection(conn)
