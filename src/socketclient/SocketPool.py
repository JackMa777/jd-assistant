# -*- coding: utf-8 -
#
# This file is part of socketpool.
# See the NOTICE for more information.

import contextlib
import time

from log import logger
from socketclient import Connector


class MaxTriesError(Exception):
    pass


class MaxConnectionsError(Exception):
    pass


class SocketPool(object):
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

    def __init__(self, factory, host=None, port=80, active_count=3, max_count=10,
                 backend_mod=None,
                 max_lifetime=600.):

        self.factory = factory
        self.host = host
        self.port = port
        self.active_count = active_count
        self.max_count = max_count
        self.backend_mod = backend_mod

        self.pool = getattr(backend_mod, 'Queue')()

        for i in range(active_count):
            try:
                new_connect = factory(host, port, backend_mod, True)
                if new_connect.is_connected():
                    self.pool.put(new_connect)
            except Exception as e:
                logger.error('新建连接异常，host：%s，port：%s，异常：%s', host, port, e)
        for i in range(max_count - active_count):
            try:
                new_connect = factory(host, port, backend_mod)
                if new_connect.is_connected():
                    self.pool.put(new_connect)
            except Exception as e:
                logger.error('新建连接异常，host：%s，port：%s，异常：%s', host, port, e)

        self._free_conns = 0
        self.max_lifetime = max_lifetime

        self.lock = self.backend_mod.RLock()

    def __del__(self):
        self.stop_reaper()

    def is_valid(self, conn: Connector, _time=time.time()):
        return not conn.is_closed() and self.max_lifetime > _time - conn.get_init_time()

    def murder_connections(self):
        current_pool_size = self.pool.qsize()
        if current_pool_size > 0:
            now = time.time()
            for candidate in self.pool:
                current_pool_size -= 1
                if self.is_valid(candidate, now):
                    self.pool.put(candidate)
                else:
                    candidate.invalidate()
                if current_pool_size <= 0:
                    break

    def start_reaper(self):
        self._reaper = self.backend_mod.ConnectionReaper(self,
                                                         delay=self.reap_delay)
        self._reaper.ensure_started()

    def stop_reaper(self):
        self._reaper.forceStop = True

    @property
    def size(self):
        return self.pool.qsize()

    def release_all(self):
        if self.pool.qsize():
            for conn in self.pool:
                conn.invalidate()

    def put_connect(self, conn: Connector):
        with self.lock:
            if self.pool.qsize() < self.max_count:
                if self.is_valid(conn):
                    self.pool.put(conn)
                else:
                    conn.invalidate()
            else:
                conn.invalidate()

    def release_connection(self, conn):
        if self._reaper is not None:
            self._reaper.ensure_started()

        self.put_connect(conn)

    def get_queue(self, host, port):
        pass

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
                for candidate in self.pool:
                    i -= 1
                    if not self.is_valid(candidate):
                        # let's drop it
                        candidate.invalidate()
                        continue

                    matches = candidate.matches(**options)
                    if not matches:
                        # let's put it back
                        unmatched.append(candidate)
                    else:
                        if candidate.is_connected():
                            found = candidate
                            break
                        else:
                            # conn is dead for some reason.
                            # reap it.
                            candidate.invalidate()

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
            self.put_connect(conn)
