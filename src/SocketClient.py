import logging
import socket
import ssl

logger = logging.getLogger()

DEFAULT_HEADERS = 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'


class SocketClient(object):
    HTTP = 80
    HTTPS = 443

    def __init__(self, conn_port=80, timeout=0.3):
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
        if isinstance(headers, dict):
            headers_list = []
            for key, value in headers.items():
                headers_list.append(f'{key}: {value}\r\n')
            headers_str = ''.join(headers_list)
        elif isinstance(headers, str):
            headers_str = headers
        else:
            # 默认添加请求头
            headers_str = DEFAULT_HEADERS.join('\r\n')
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
        host_split = host.split('.')
        domain = '.'.join(host_split[len(host_split) - 2:])
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
        b_msg_list = [f'{method} {"".join(uri_list)} HTTP/1.1\r\nHost: {host}\r\n']
        if data:
            data_str = None
            if isinstance(data, dict):
                data_list = []
                for key, value in data.items():
                    data_list.append(f'&{key}={value}')
                data_str = ''.join(data_list)[1:]
                headers_str = f'{headers_str}Content-Type: application/x-www-form-urlencoded;charset=UTF-8\r\n'
            elif isinstance(data, str):
                data_str = data
                headers_str = f'{headers_str}Content-Type: application/json;charset=UTF-8\r\n'
            b_msg_list.append(f'{headers_str}Connection: keep-alive\r\n\r\n')
            if data_str is not None:
                b_msg_list.append(data_str)
        else:
            b_msg_list.append(f'{headers_str}Connection: keep-alive\r\n\r\n')
        if domain not in self.connected_set:
            # 连接服务器
            sock.connect((host, self.conn_port))
            self.connected_set.add(domain)
        # 发送报文
        # print(''.join(b_msg_list))
        sock.send(''.join(b_msg_list).encode())

        if res_func:
            res_func(self.sock)
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
