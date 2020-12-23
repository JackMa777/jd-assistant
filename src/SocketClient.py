import socket
import ssl

DEFAULT_HEADERS = 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'


class SocketClient(socket.socket):
    HTTP = 80
    HTTPS = 443

    def __init__(self, conn_port=80, timeout=0.1):
        socket.socket.__init__(self, socket.AF_INET, socket.SOCK_STREAM)
        if conn_port == SocketClient.HTTP:
            pass
        elif conn_port == SocketClient.HTTPS:
            self = ssl.wrap_socket(self)
        else:
            raise Exception("端口错误")
        self.conn_port = conn_port
        self.settimeout(timeout)

    def send_http_request(self, url, method='GET', params=dict, headers=dict, resFunc=None):
        # 默认添加请求头
        if headers is None:
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
        # 连接服务器
        self.connect((url_split[0], self.conn_port))
        # 发送报文处理
        # TODO 处理params数据
        # TODO 处理headers数据
        bMsg = f'{method} /{url_split[1]} HTTP/1.1\r\n' \
               f'Host: {url_split[0]}\r\n' \
               f'{headers}\r\n' \
               'Connection: keep-alive\r\n\r\n'
        # 发送报文
        self.send(bMsg.encode())

        if resFunc:
            resFunc(self)
        else:
            html = ''
            charset = 'utf-8'
            # 接收html字节数据
            while True:
                data = self.recv(1024)
                if data:
                    try:
                        html += data.decode(charset)
                    except Exception as e:
                        pass
                else:
                    break
            # 保持连接
            return html

    def close_client(self):
        self.close()
