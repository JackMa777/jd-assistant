import contextlib
import logging
from http import client

from urllib3 import HTTPResponse

import cookie_util
from socketclient.Connector import TcpConnector
from socketclient.SocketPoolManager import SocketPoolManager
from socketclient.util import load_backend

logger = logging.getLogger()

DEFAULT_HEADERS = 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'


class SocketClient(object):

    def __init__(self, conn_factory=TcpConnector, backend="thread", retry_max=3, retry_delay=.01):
        # backend="thread"
        # backend="gevent"
        if isinstance(backend, str):
            self.backend_mod = load_backend(backend)
            self.backend = backend
        else:
            self.backend_mod = backend
            self.backend = str(getattr(backend, '__name__', backend))
        self.pool_manager = SocketPoolManager(conn_factory=conn_factory, backend_mod=self.backend_mod)
        self.retry_max = retry_max
        self.retry_delay = retry_delay

    def init_pool(self, host=None, port=80, active_count=3, max_count=10):
        self.pool_manager.init_pool(host, port, active_count, max_count)

    @contextlib.contextmanager
    def get_connect(self, host=None, port=80):
        conn = None
        pool = self.pool_manager.get_pool(host, port)
        if pool:
            tries = 0
            while tries < self.retry_max:
                try:
                    conn = pool.get_connect(host, port)
                    break
                except Exception as e:
                    logger.error('获取连接异常，重试第：%s次，异常：%s', tries, e)
                tries += 1
                self.backend_mod.sleep(self.retry_delay)
        try:
            yield conn
        except Exception as e:
            conn.handle_exception(e)
        finally:
            self.pool_manager.put_connect(conn)

    # 修改为连接所有
    def connect(self, host=None, port=80):
        if host is not None and port is not None:
            pool = self.pool_manager.get_pool(host, port)
            if pool:
                pool.connect_all()
        else:
            self.pool_manager.connect_all()

    @staticmethod
    def mark_byte_msg(url, method='GET', params=None, data=None, headers=None, cookies=None):
        # http协议处理
        if 'http://' in url:
            url = url.replace('http://', '')
        # https协议处理
        if 'https://' in url:
            url = url.replace('https://', '')
        url = url if '/' in url else url + '/'
        url_split = url.split('/', 1)
        host = url_split[0]
        uri_list = ['/', url_split[1]]
        if params:
            uri_list.append('?')
            if isinstance(params, dict):
                params_list = []
                for key, value in params.items():
                    params_list.append(f'&{key}={value}')
                uri_list.append(''.join(params_list)[1:])
            elif isinstance(params, str):
                uri_list.append(params)
        # 处理报文
        b_msg_array = bytearray()
        if isinstance(headers, dict):
            headers_list = []
            for key, value in headers.items():
                if key.lower() == 'cookie' and cookies is None:
                    cookies = value
                else:
                    headers_list.append(f'{key}: {value}\r\n')
            headers_str = ''.join(headers_list)
        elif isinstance(headers, str):
            headers_str = headers
        else:
            # 默认添加请求头
            headers_str = f'{DEFAULT_HEADERS}\r\n'
        msg_list = [f'{method} {"".join(uri_list)} HTTP/1.1\r\nHost: {host}\r\n']
        if cookies is not None and cookies != '':
            headers_str = f'{headers_str}Cookie: {cookie_util.get_cookies_str(cookies)}\r\n'
        if data:
            content_len = 0
            data_bytes = None
            if isinstance(data, dict):
                data_list = []
                for key, value in data.items():
                    data_list.append(f'&{key}={value}')
                data_bytes = ''.join(data_list)[1:].encode()
                headers_str = f'{headers_str}Content-Type: application/x-www-form-urlencoded;charset=UTF-8\r\n'
            elif isinstance(data, str):
                data_bytes = data.encode()
                headers_str = f'{headers_str}Content-Type: application/json;charset=UTF-8\r\n'
            if data_bytes is not None:
                content_len = len(data_bytes)
            msg_list.append(f'{headers_str}Content-Length: {content_len}\r\nConnection: keep-alive\r\n\r\n')
            b_msg_array.extend(''.join(msg_list).encode())
            if content_len != 0:
                b_msg_array.extend(data_bytes)
        else:
            msg_list.append(f'{headers_str}Connection: keep-alive\r\n\r\n')
            b_msg_array.extend(''.join(msg_list).encode())
        return bytes(b_msg_array)

    def send(self, host=None, port=80, byte_msg: bytes = b''):
        with self.get_connect(host, port) as conn:
            # 发送报文
            conn.send(byte_msg)
            logger.info('已发送')

    def get_http_response(self, sock):
        charset = 'utf-8'
        _UNKNOWN = 'UNKNOWN'
        http_response = None
        # 接收html字节数据
        r = client.HTTPResponse(sock)
        try:
            try:
                r.begin()
            except ConnectionError as ce:
                logger.error('拉取数据异常：%s', ce)
            will_close = r.will_close
            http_response = HTTPResponse.from_httplib(r)
            if will_close and will_close != _UNKNOWN:
                logger.info('数据已接收，主机关闭了连接')
                self.close_client()
        except Exception as e:
            logger.error('数据接收异常：%s', e)
        finally:
            r.close()
            # print('response：')
            # print(response.decode(charset))
            # 保持连接
            if http_response is not None:
                setattr(http_response, "body", http_response.data.decode(charset))
                return http_response
            else:
                return None

    def send_http_request(self, url, method='GET', params=None, data=None, headers=None, cookies=None, res_func=None):
        if 'http://' in url:
            tmp_url = url.replace('http://', '')
            port = 80
        elif 'https://' in url:
            tmp_url = url.replace('https://', '')
            port = 443
        else:
            raise Exception("端口错误")
        byte_msg = SocketClient.mark_byte_msg(url, method, params, data, headers, cookies)
        tmp_url = tmp_url if '/' in tmp_url else tmp_url + '/'
        host = tmp_url.split('/', 1)[0]
        with self.get_connect(host, port) as conn:
            # 发送报文
            conn.send(byte_msg)
            logger.info('已发送')
            # print(byte_msg)
            # 读取报文
            if res_func:
                response = res_func(conn)
            else:
                response = conn.do_func(self.get_http_response)
        return response

    def close_client(self):
        self.pool_manager.clear_pools()
