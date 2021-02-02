import time
from http import cookiejar
from http.cookiejar import CookieJar

from requests import cookies


# reference code form: http.cookiejar.parse_ns_headers
def mark_cookie(tup):
    name, value, standard, rest = tup
    domain = standard.get("domain", Absent)
    path = standard.get("path", Absent)
    port = standard.get("port", Absent)
    expires = standard.get("expires", Absent)

    # set the easy defaults
    version = standard.get("version", None)
    if version is not None:
        try:
            version = int(version)
        except ValueError:
            return None  # invalid version, ignore cookie
    secure = standard.get("secure", False)
    # (discard is also set if expires is Absent)
    discard = standard.get("discard", False)
    comment = standard.get("comment", None)
    comment_url = standard.get("commenturl", None)

    # set default path
    if path is not Absent and path != "":
        path_specified = True
        path = escape_path(path)
    else:
        path_specified = False
        path = request_path(request)
        i = path.rfind("/")
        if i != -1:
            if version == 0:
                # Netscape spec parts company from reality here
                path = path[:i]
            else:
                path = path[:i + 1]
        if len(path) == 0: path = "/"

    # set default domain
    domain_specified = domain is not Absent
    # but first we have to remember whether it starts with a dot
    domain_initial_dot = False
    if domain_specified:
        domain_initial_dot = bool(domain.startswith("."))
    if domain is Absent:
        req_host, erhn = eff_request_host(request)
        domain = erhn
    elif not domain.startswith("."):
        domain = "." + domain

    # set default port
    port_specified = False
    if port is not Absent:
        if port is None:
            # Port attr present, but has no value: default to request port.
            # Cookie should then only be sent back on that port.
            port = request_port(request)
        else:
            port_specified = True
            port = re.sub(r"\s+", "", port)
    else:
        # No port attr present.  Cookie can be sent back on any port.
        port = None

    # set default expires and discard
    if expires is Absent:
        expires = None
        discard = True
    elif expires <= self._now:
        # Expiry date in past is request to delete cookie.  This can't be
        # in DefaultCookiePolicy, because can't delete cookies there.
        try:
            self.clear(domain, path, name)
        except KeyError:
            pass
        _debug("Expiring cookie, domain='%s', path='%s', name='%s'",
               domain, path, name)
        return None

    return Cookie(version,
                  name, value,
                  port, port_specified,
                  domain, domain_specified, domain_initial_dot,
                  path, path_specified,
                  secure,
                  expires,
                  discard,
                  comment,
                  comment_url,
                  rest)


def merge_cookies_from_response(cookie_jar, http_response):
    cookie_list_str = http_response.info().getlist('set-cookie')
    cookie_jar._now = int(time.time())
    cookie_set = cookiejar.parse_ns_headers(cookie_list_str)
    cookie_tuples = cookie_jar._normalized_cookie_tuples(cookie_set)

    for tup in cookie_tuples:
        cookie = mark_cookie(tup)
        if cookie:
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


class Absent:
    pass
