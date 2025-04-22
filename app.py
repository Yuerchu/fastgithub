# -*- coding: utf-8 -*-

# 引入库
from fastapi import (FastAPI, Request)
from fastapi.responses import (Response, RedirectResponse, JSONResponse)
from fastapi.exceptions import HTTPException
import config
from urllib.parse import quote
import requests
from requests.utils import (
    stream_decode_response_unicode, iter_slices, CaseInsensitiveDict)
import re

# 加载配置文件
cfg = config.Config()

jsdelivr = cfg.get('jsdelivr')

"""
  先生效白名单再匹配黑名单，pass_list匹配到的会直接302到jsdelivr而忽略设置
  生效顺序 白->黑->pass，可以前往https://github.com/hunshcn/gh-proxy/issues/41 查看示例
  每个规则一行，可以封禁某个用户的所有仓库，也可以封禁某个用户的特定仓库，下方用黑名单示例，白名单同理
  user1 # 封禁user1的所有仓库
  user1/repo1 # 封禁user1的repo1
  */repo1 # 封禁所有叫做repo1的仓库
"""
white_list = '''
'''
black_list = '''
'''
pass_list = '''
'''

# 正则匹配请求
exp1 = re.compile(r'^(?:https?://)?github\.com/(?P<author>.+?)/(?P<repo>.+?)/(?:releases|archive)/.*$')
exp2 = re.compile(r'^(?:https?://)?github\.com/(?P<author>.+?)/(?P<repo>.+?)/(?:blob|raw)/.*$')
exp3 = re.compile(r'^(?:https?://)?github\.com/(?P<author>.+?)/(?P<repo>.+?)/(?:info|git-).*$')
exp4 = re.compile(r'^(?:https?://)?raw\.(?:githubusercontent|github)\.com/(?P<author>.+?)/(?P<repo>.+?)/.+?/.+$')
exp5 = re.compile(r'^(?:https?://)?gist\.(?:githubusercontent|github)\.com/(?P<author>.+?)/.+?/.+$')

# 配置默认请求头
requests.sessions.default_headers = lambda: CaseInsensitiveDict()

def iter_content(self, chunk_size=1, decode_unicode=False):
    """对请求函数重写, 将 decode_content 设置为 False"""

    def generate():
        # Special case for urllib3.
        if hasattr(self.raw, 'stream'):
            try:
                for chunk in self.raw.stream(chunk_size, decode_content=False):
                    yield chunk
            except Exception as e:
                raise HTTPException(status_code=500, detail=e)
                
        else:
            # Standard file-like object.
            while True:
                chunk = self.raw.read(chunk_size)
                if not chunk:
                    break
                yield chunk

        self._content_consumed = True

    if self._content_consumed and isinstance(self._content, bool):
        raise HTTPException(status_code=500, detail="Stream has already been consumed.")
    elif chunk_size is not None and not isinstance(chunk_size, int):
        raise TypeError("chunk_size must be an int, it is instead a %s." % type(chunk_size))
    # simulate reading small chunks of the content
    reused_chunks = iter_slices(self._content, chunk_size)

    stream_chunks = generate()

    chunks = reused_chunks if self._content_consumed else stream_chunks

    if decode_unicode:
        chunks = stream_decode_response_unicode(chunks, self)

    return chunks

def check_url(u):
    for exp in (exp1, exp2, exp3, exp4, exp5):
        m = exp.match(u)
        if m:
            return m
    return False

def proxy(u, allow_redirects=False):
    headers = {}
    r_headers = dict(Request.headers)
    if 'Host' in r_headers:
        r_headers.pop('Host')
    try:
        url = u + Request.url.replace(Request.base_url, '', 1)
        if url.startswith('https:/') and not url.startswith('https://'):
            url = 'https://' + url[7:]
        r = requests.request(method=Request.method, url=url, data=Request.data, headers=r_headers, stream=True, allow_redirects=allow_redirects)
        headers = dict(r.headers)

        if 'Content-length' in r.headers and int(r.headers['Content-length']) > cfg.get('size_limit'):
            return RedirectResponse(u + Request.url.replace(Request.base_url, '', 1))

        def generate():
            for chunk in iter_content(r, chunk_size=cfg.get('chunk_size')):
                yield chunk

        if 'Location' in r.headers:
            _location = r.headers.get('Location')
            if check_url(_location):
                headers['Location'] = '/' + _location
            else:
                return proxy(_location, True)

        return Response(generate(), headers=headers, status=r.status_code)
    except Exception as e:
        headers['content-type'] = 'text/html; charset=UTF-8'
        return JSONResponse(
            status_code=500,
            content='server error ' + str(e), 
            headers=headers)

app = FastAPI(
    title='FastGithub',
    openapi_url='openapi.json' if cfg.get('debug') else None
)

@app.get('/<path:u>')
@app.post('/<path:u>')
def handler(u):
    u = u if u.startswith('http') else 'https://' + u
    if u.rfind('://', 3, 9) == -1:
        u = u.replace('s:/', 's://', 1)  # uwsgi会将//传递为/
    pass_by = False
    m = check_url(u)
    if m:
        m = tuple(m.groups())
        if white_list:
            for i in white_list:
                if m[:len(i)] == i or i[0] == '*' and len(m) == 2 and m[1] == i[1]:
                    break
            else:
                return Response('Forbidden by white list.', status=403)
        for i in black_list:
            if m[:len(i)] == i or i[0] == '*' and len(m) == 2 and m[1] == i[1]:
                return Response('Forbidden by black list.', status=403)
        for i in pass_list:
            if m[:len(i)] == i or i[0] == '*' and len(m) == 2 and m[1] == i[1]:
                pass_by = True
                break
    else:
        return Response('Invalid input.', status=403)

    if (jsdelivr or pass_by) and exp2.match(u):
        u = u.replace('/blob/', '@', 1).replace('github.com', 'cdn.jsdelivr.net/gh', 1)
        return RedirectResponse(u)
    elif (jsdelivr or pass_by) and exp4.match(u):
        u = re.sub(r'(\.com/.*?/.+?)/(.+?/)', r'\1@\2', u, 1)
        _u = u.replace('raw.githubusercontent.com', 'cdn.jsdelivr.net/gh', 1)
        u = u.replace('raw.github.com', 'cdn.jsdelivr.net/gh', 1) if _u == u else _u
        return RedirectResponse(u)
    else:
        if exp2.match(u):
            u = u.replace('/blob/', '/raw/', 1)
        if pass_by:
            url = u + Request.url.replace(Request.base_url, '', 1)
            if url.startswith('https:/') and not url.startswith('https://'):
                url = 'https://' + url[7:]
            return RedirectResponse(url)
        u = quote(u, safe='/:')
        return proxy(u)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app='app:app',
        host=cfg.get('host'),
        port=cfg.get('port'),
        reload=cfg.get('debug'),
        log_level='debug' if cfg.get('debug') else 'info',
    )