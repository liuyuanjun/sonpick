'''
Function:
    Implementation of JooxMusicClient Cookies Builder
Author:
    Zhenchao Jin
WeChat Official Account (微信公众号):
    Charles的皮卡丘
'''
import re
import json
import time
import hashlib
import requests
from urllib.parse import quote


'''settings'''
USERNAME = 'YOUR Email'
PASSWORD = 'YOUR PASSWORD'
COUNTRY = "hk"
LANG = "zh_TW"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*", "Origin": "https://www.joox.com", "Referer": "https://www.joox.com/",
}


'''buildjooxcookies'''
def buildjooxcookies():
    session, ts = requests.Session(), int(time.time() * 1000); session.headers.update(HEADERS)
    enc_email, md5_pw = quote(quote(USERNAME)), hashlib.md5(PASSWORD.encode("utf-8")).hexdigest()
    url = (f"https://api.joox.com/web-fcgi-bin/web_wmauth?country={COUNTRY}&lang={LANG}&wxopenid={enc_email}&password={md5_pw}&wmauth_type=0&authtype=2&time={ts}&_={ts}&callback=axiosJsonpCallback6")
    (resp := session.get(url=url, timeout=20)).raise_for_status()
    m = re.search(r"\{.*\}", resp.text, re.S)
    body = json.loads(m.group(0)) if m else {}
    if body.get("code") not in (0, None): raise SystemExit(f"login rejected: {body}")
    wmid, skey = body.get("wmid"), body.get("session_key")
    if not (wmid and skey): raise SystemExit(f"login gave no session_key. body={body}")
    cookies: dict = requests.utils.dict_from_cookiejar(resp.cookies)
    cookies.update(requests.utils.dict_from_cookiejar(session.cookies))
    creds = {"cookies": cookies, "body": body, "wmid": str(wmid), "session_key": skey, "country": body.get("country") or COUNTRY, "user_type": body.get("user_type"), "nickname": body.get("nickname")}
    return creds


'''tests'''
if __name__ == '__main__':
    print(buildjooxcookies())