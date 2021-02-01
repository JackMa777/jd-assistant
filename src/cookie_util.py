from http import cookiejar
from http.cookiejar import CookieJar
from urllib.request import Request

from requests import cookies, utils


def mark_request(url, method='GET', params=None, data=None, headers=None, cookies=None):
    req = Request(
        method=method.upper(),
        url=url,
        headers=headers,
        files=files,
        data=data or {},
        json=json,
        params=params or {},
        auth=auth,
        cookies=cookies,
        hooks=hooks,
    )
    p = PreparedRequest()
    p.prepare(
        method=method.upper(),
        url=url,
        # files=files,
        data=data,
        # json=json,
        headers=headers,
        params=params,
        # auth=merge_setting(auth, self.auth),
        cookies=merge_cookies(merge_cookies(RequestsCookieJar(), self.cookies), cookies),
        # hooks=hooks,
    )


def merge_cookies(cookie_jar, http_response):
    # TODO
    p = PreparedRequest()
    p.prepare(
        method=method.upper(),
        url=url,
        # files=files,
        data=data,
        # json=json,
        headers=headers,
        params=params,
        # auth=merge_setting(auth, self.auth),
        cookies=merge_cookies(merge_cookies(RequestsCookieJar(), self.cookies), cookies),
        # hooks=hooks,
    )

    # for cookie in self.http_response.info().getlist('set-cookie'):
    #     cookiejar.parse_ns_headers(cookie)
    cookie_list = http_response.info().getlist('set-cookie')
    cookie_set = cookiejar.parse_ns_headers(cookie_list)

    cookie_tuples = cookie_jar._normalized_cookie_tuples(cookie_set)
    cookies = []
    for tup in cookie_tuples:
        cookie = cookie_jar._cookie_from_cookie_tuple(tup, request)
        if cookie:
            cookies.append(cookie)
    for cookie in cookies:
        cookie_jar.set_cookie(cookie)
    return cookie_jar


def get_cookies_str(cookie):
    if isinstance(cookie, CookieJar):
        return cookie.__str__()
    elif isinstance(cookie, dict):
        return cookies.cookiejar_from_dict(cookie).__str__()
    elif isinstance(cookie, str):
        return cookies
    else:
        return ''
