import logging
import socket
import ssl
from http import client

from urllib3 import HTTPResponse

import cookie_util

logger = logging.getLogger()

DEFAULT_HEADERS = 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'


class SocketClient(object):
    HTTP = 80
    HTTPS = 443

    def __init__(self, conn_port=80, conn_host=None, timeout=0.5):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 禁用Nagle算法
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if conn_port == SocketClient.HTTP:
            pass
        elif conn_port == SocketClient.HTTPS:
            sock = ssl.wrap_socket(sock)
        else:
            raise Exception("端口错误")
        # TODO 改造成socket连接池
        self.sock = sock
        self.conn_port = conn_port
        self.is_connected = False
        self.is_closed = False
        if conn_host is not None:
            host_split = conn_host.split('.')
            domain = '.'.join(host_split[len(host_split) - 2:])
            self.conn_host = conn_host
            self.domain = domain
        else:
            self.domain = None
        self.sock.setblocking(True)
        self.sock.settimeout(timeout)

    def connect(self, host=None):
        # TODO 与socket连接池联动改造
        connected = self.is_connected
        domain = self.domain
        if host is not None:
            host_split = host.split('.')
            connect_domain = '.'.join(host_split[len(host_split) - 2:])
            if domain is not None:
                if domain != connect_domain:
                    if connected:
                        raise Exception('输入主机域名与该套接字已连接主机域名不一致')
                    else:
                        raise Exception('输入主机域名与该套接字已设置主机域名不一致')
                elif connected:
                    return
            elif connected:
                return
        else:
            if connected:
                return
            host = self.conn_host
            if host is None:
                raise Exception('该socket初始化时未添加host参数')
            connect_domain = domain
        # 连接服务器
        self.sock.connect((host, self.conn_port))
        logger.info(f'已与 {host} 连接')
        self.is_connected = True
        self.domain = connect_domain

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

    def send(self, byte_msg: bytes):
        self.sock.send(byte_msg)

    def get_http_response(self, recv_func=None):
        sock = self.sock
        charset = 'utf-8'
        _UNKNOWN = 'UNKNOWN'
        http_response = None
        # 接收html字节数据
        if recv_func:
            return recv_func(sock)
        else:
            r = client.HTTPResponse(sock)
            try:
                try:
                    r.begin()
                except ConnectionError as ce:
                    logger.error('拉取数据异常：%s', ce)
                will_close = r.will_close
                http_response = HTTPResponse.from_httplib(r)
                if will_close and will_close != _UNKNOWN:
                    logger.info('数据已接收，主机 %s 关闭了连接', self.conn_host)
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
        # http协议处理
        tmp_url = None
        if 'http://' in url:
            if self.conn_port != SocketClient.HTTP:
                raise Exception(f"该socket初始端口为:{self.conn_port}，请输入https地址")
            tmp_url = url.replace('http://', '')
        # https协议处理
        if 'https://' in url:
            if self.conn_port != SocketClient.HTTPS:
                raise Exception(f"该socket初始端口为:{self.conn_port}，请输入http地址")
            tmp_url = url.replace('https://', '')
        byte_msg = SocketClient.mark_byte_msg(url, method, params, data, headers, cookies)
        tmp_url = tmp_url if '/' in tmp_url else tmp_url + '/'
        host = tmp_url.split('/', 1)[0]
        self.connect(host)
        # 发送报文
        # print(byte_msg)
        self.send(byte_msg)
        logger.info('已发送')
        # 读取报文
        return self.get_http_response(res_func)

    def close_client(self):
        # TODO 与socket连接池联动改造
        self.sock.close()
        self.is_closed = True
