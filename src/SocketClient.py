import logging
import socket
import ssl

logger = logging.getLogger()

DEFAULT_HEADERS = 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'


class SocketClient(object):
    HTTP = 80
    HTTPS = 443

    def __init__(self, conn_port=80, timeout=0.1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if conn_port == SocketClient.HTTP:
            pass
        elif conn_port == SocketClient.HTTPS:
            sock = ssl.wrap_socket(sock)
        else:
            raise Exception("端口错误")
        self.sock = sock
        self.connected_set = set()
        self.conn_port = conn_port
        self.sock.settimeout(timeout)

    def send_http_request(self, url, method='GET', params=None, data=None, headers=None, res_func=None):
        sock = self.sock
        if headers:
            # TODO 处理headers数据
            pass
        else:
            # 默认添加请求头
            headers = DEFAULT_HEADERS
        # http协议处理
        if 'http://' in url:
            if self.conn_port != SocketClient.HTTP:
                raise Exception(f"该socket初始端口为:{self.conn_port}，请输入https地址")
            url = url.replace('http://', '')
        # https协议处理
        if 'https://' in url:
            if self.conn_port != SocketClient.HTTPS:
                raise Exception(f"该socket初始端口为:{self.conn_port}，请输入http地址")
            url = url.replace('https://', '')
        url = url if '/' in url else url + '/'
        url_split = url.split('/', 1)
        host = url_split[0]
        uri = '/' + url_split[1]
        if host not in self.connected_set:
            # 连接服务器
            sock.connect((host, self.conn_port))
            self.connected_set.add(host)
        if params:
            # TODO 处理params数据
            uri = uri + '?' + params
        else:
            pass
        # 处理报文
        b_msg = f'{method} {uri} HTTP/1.1\r\n' \
                f'Host: {host}\r\n' \
                f'{headers}\r\n' \
                'Connection: keep-alive\r\n\r\n'
        if data:
            # TODO 处理data数据
            b_msg = b_msg + data
        else:
            pass
        # 发送报文
        sock.send(b_msg.encode())

        if res_func:
            res_func(self)
        else:
            # TODO 解析页面
            html = ''
            charset = 'utf-8'
            # 接收html字节数据
            while True:
                data = self.sock.recv(1024)
                if data:
                    try:
                        html += data.decode(charset)
                    except Exception as e:
                        logger.error('页面解析异常：%s', e)
                        return html
                else:
                    break
            # 保持连接
            return html

    def close_client(self):
        self.sock.close()
