# -*- coding: utf-8 -
#
# This file is part of socketpool.
# See the NOTICE for more information.

import eventlet
from eventlet.green import select
from eventlet.green import socket
from eventlet import queue

from socketpool.pool import ConnectionPool

sleep = eventlet.sleep
Socket = socket.socket
Select = select.select
Semaphore = eventlet.semaphore.BoundedSemaphore
