import ssl


def get_new_session(*, proxy=None, **kwargs):
    try:
        import httpx
    except ImportError:
        httpx = None
    if httpx is not None and ssl.OPENSSL_VERSION_INFO >= (1, 0, 2):
        kwargs.setdefault("timeout", 30)
        kwargs.setdefault("follow_redirects", True)
        if "transport" not in kwargs:
            proxy_config = httpx.Proxy(proxy) if proxy is not None else None
            kwargs["transport"] = httpx.HTTPTransport(retries=10, proxy=proxy_config)
        return httpx.Client(**kwargs)

    import requests
    from requests.adapters import HTTPAdapter

    class Session(requests.Session):
        def request(self, method, url, **options):
            options.setdefault("timeout", 30)
            return super().request(method, url, **options)

    session = Session()
    session.mount("http://", HTTPAdapter(max_retries=10))
    session.mount("https://", HTTPAdapter(max_retries=10))
    if proxy is not None:
        session.trust_env = False
        session.proxies.update({"http": proxy, "https": proxy})
    return session


def get_new_session_use_proxy(http_proxy: str):
    proxy = http_proxy.strip()
    if "://" not in proxy:
        proxy = f"http://{proxy}"
    return get_new_session(proxy=proxy)


http = get_new_session()
