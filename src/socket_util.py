import socket
import ssl


def send_request_by_socket(url, method='GET', params=None, headers=None, resFunc=None):
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # 默认添加请求头
    if headers == None:
        headers = 'User-Agent: Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)'
    # http协议处理
    if 'http://' in url:
        url = url.replace('http://', '')
        port = 80
    # https协议处理
    if 'https://' in url:
        conn = ssl.wrap_socket(conn)
        url = url.replace('https://', '')
        port = 443
    url = url if '/' in url else url + '/'
    urlSplit = url.split('/', 1)
    # 连接服务器
    conn.connect((urlSplit[0], port))

    # 发送报文处理
    # TODO 处理method
    # TODO 处理params数据
    bMsg = f'{method} /{urlSplit[1]} HTTP/1.1\r\nHost: {urlSplit[0]}\r\n{headers}\r\nConnection: close\r\n\r\n'

    # 发送报文
    conn.send(bMsg.encode())

    if resFunc:
        resFunc(conn)
        conn.close()
    else:
        html = ''
        charset = 'utf-8'
        # 接收html字节数据
        while True:
            data = conn.recv(1024)
            if data:
                try:
                    html += data.decode(charset)
                except Exception as e:
                    pass
            else:
                conn.close()
                break
        return html