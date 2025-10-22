import re
import json
import asyncio
import aiohttp
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("cstatcheck", "badbirdy", "一个简单的 cs 战绩查询插件", "1.0.0")
class Player(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir()

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        PLAYER_PATH = self.data_dir
    
        # 确保数据目录存在
        self.data_dir.mkdir(exist_ok=True)
    # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """这是一个 hello world 指令""" # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
        user_name = event.get_sender_name()
        message_str = event.message_str # 用户发的纯文本消息字符串
        message_chain = event.get_messages() # 用户所发的消息的消息链 # from astrbot.api.message_components import *
        logger.info(message_chain)
        yield event.plain_result(f"Hello, {user_name}, 你发了 {message_str}!") # 发送一条纯文本消息

	# 根据用户输入的 username 获取 domain
    async def get_domain(session: aiohttp.ClientSession, username: str):
        # URL encode 用户名
        username_encoded = urllib.parse.quote(username)

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.6,zh-HK;q=0.4,en;q=0.2",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "keep-alive",
            "Referer": f"https://arena.5eplay.com/search?keywords={username_encoded}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "TE": "trailers",
            # "Cookie": "ssxmod_itna=...; 5ewin_session_=...",
        }

        url = "https://arena.5eplay.com/api/search/player/1/16"
        params = {"keywords": username}

        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status != 200:
                print(f"获取domain失败：HTTP {resp.status}")
                return None
            data = await resp.json()

            users = data.get("data", {}).get("user", {}).get("list", [])
            for u in users:
                if u.get("username") == username:
                    return u.get("domain")
            return None

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
