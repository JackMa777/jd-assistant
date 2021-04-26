# -*- coding: utf-8 -
#
# This file is part of socketpool.
# See the NOTICE for more information.

import select
import socket
import threading
import time
import weakref

try:
    import Queue as queue
except ImportError:  # py3
    import queue

Select = select.select
Socket = socket.socket
sleep = time.sleep
Semaphore = threading.BoundedSemaphore
