import re
import json
import asyncio
import urllib.parse
import aiohttp
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger

@register("cstatcheck", "badbirdy", "一个简单的 cs 战绩查询插件", "1.0.0")
class Player(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir()
        self.user_data_file = self.data_dir / "user_data.json"

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
    
        # 确保数据目录存在
        self.data_dir.mkdir(exist_ok=True)
        # 如果用户数据文件不存在，则创建一个空的 JSON 文件
        if not self.user_data_file.exists():
            with open(self.user_data_file, "w", encoding="utf-8") as f:
                json.dump({}, f)

    # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """这是一个 hello world 指令""" # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
        user_name = event.get_sender_name()
        message_str = event.message_str # 用户发的纯文本消息字符串
        message_chain = event.get_messages() # 用户所发的消息的消息链 # from astrbot.api.message_components import *
        logger.info(message_chain)
        yield event.plain_result(f"Hello, {user_name}, 你发了 {message_str}!") # 发送一条纯文本消息

    async def get_domain(session: aiohttp.ClientSession, playername: str, event: AstrMessageEvent):
        """根据用户输入的 playername 获取 domain"""
        # URL encode 用户名
        playername_encoded = urllib.parse.quote(playername)
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.6,zh-HK;q=0.4,en;q=0.2",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "keep-alive",
            "Referer": f"https://arena.5eplay.com/search?keywords={playername_encoded}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "TE": "trailers",
            # "Cookie": "ssxmod_itna=...; 5ewin_session_=...",
        }
        url = "https://arena.5eplay.com/api/search/player/1/16"
        params = {"keywords": playername}

        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status != 200:
                print(f"获取domain失败：HTTP {resp.status}")
                return None
            data = await resp.json()

            users = data.get("data", {}).get("user", {}).get("list", [])
            for u in users:
                if u.get("username") == playername:
                    return u.get("domain")
            return None

    async def get_uuid(session: aiohttp.ClientSession, domain: str):
        """根据 domain 获取 uuid"""
        post_url = "https://gate.5eplay.com/userinterface/http/v1/userinterface/idTransfer"
        post_headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0",
            "Accept": "*/*",
            "Accept-Language": "zh-cn",
            "Content-Type": "application/json",
            "x-ca-key": "5eplay",
            "x-ca-signature-method": "HmacSHA256",
            "x-ca-signature": "CJNeR4KLRxYAB1Ifb/muzBxy4SkMNhLARwfx7ILtHRY=",
            "x-ca-signature-headers": "Accept-Language,Authorization",
            "Origin": "https://arena-next.5eplaycdn.com",
            "Referer": "https://arena-next.5eplaycdn.com/",
        }
        post_data = {
            "trans": {
                "domain": domain
            }
        }

        async with session.post(post_url, json=post_data, headers=post_headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
            uuid = data.get("data", {}).get("uuid")
            return uuid

    async def get_match_id(self, session: aiohttp.ClientSession,uuid):
        """根据 uuid 获取最近一把比赛的 match_id"""
        get_url = f"https://gate.5eplay.com/crane/http/api/data/player_match?uuid={uuid}"
        real_url = "https://gate.5eplay.com/crane/http/api/data/player_match?uuid=abee0c4d-aa77-11ef-848e-506b4bfa3106"
        get_headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0",
            "Accept": "*/*",
            "Accept-Language": "zh-cn",
            "Authorization": "",
            "x-ca-key": "5eplay",
            "Host": "gate.5eplay.com",
            "x-ca-signature-method": "HmacSHA256",
            "x-ca-signature": "8rrdm62A4ISHZDa9tBxXdMyVqA6xdUy5idiO4+4NTIc=",
            "x-ca-signature-headers": "Accept-Language,Authorization",
            "Origin": "https://arena-next.5eplaycdn.com",
            "Referer": "https://arena-next.5eplaycdn.com/",
            "TE": "trailers",
        }

        async with session.get(get_url, headers=get_headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
            match_list = data.get("data", {}).get("match_data", [])
            if match_list:
                return match_list[0].get("match_id")
            return None

    async def get_match_stats(self, session: aiohttp.ClientSession, match_id):
        """根据 match_id 获取比赛数据"""
        get_url = f"https://gate.5eplay.com/crane/http/api/data/match_info?match_id={match_id}"
        get_headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0",
            "Accept": "*/*",
            "Accept-Language": "zh-cn",
            "Authorization": "",
            "Content-Type": "application/json",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "Priority": "u=4",
            "Origin": "https://arena-next.5eplaycdn.com",
            "Referer": "https://arena-next.5eplaycdn.com/",
            "TE": "trailers",
        }

        async with session.get(get_url, headers=get_headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("data", {})

    async def process_json(self, json_data):
        """处理比赛数据，提取并格式化战绩信息"""
        # 这里根据实际的 json 结构提取所需信息
        basic_info = json_data.get("data", {}).get("main", {})
        group_1 = json_data.get("data", {}).get("group_1", [])
        group_2 = json_data.get("data", {}).get("group_2", [])
        #todo: 处理数据，提取战绩信息

    @filter.regex(r"^(?:添加用户|用户|添加玩家|玩家)\s*(.+)")
    async def add_player_data(self, playername: str):
        """响应用户添加玩家请求，并进行将玩家数据进行存储"""

        full_text = event.message_str.strip()
        playername = re.match(r"^(?:添加用户|用户|添加玩家|玩家)\s*(.+)", full_text)
        username = event.get_sender_name()
        domain = None
        uuid = None

        # todo:a function to judge whether the player has been added
        '''
        if player_added:
            yield event.plain_result("玩家已被添加")
        '''
        async with aiohttp.ClientSession() as session:
            domain = await self.get_domain(session, playername)
            if not domain:
                return f"未找到玩家 {playername} 的 domain 信息。"
            uuid = await self.get_uuid(session, domain)
            if not uuid:
                return f"未找到玩家 {playername} 的 UUID 信息。"
        
        # 存储玩家信息到 JSON 文件
        player_data = {}
        if self.user_data_file.exists():
            with open(self.user_data_file, "r", encoding="utf-8") as f:
                player_data = json.load(f)
        player_data[username] = {
            "name": playername,
            "domain": domain,
            "uuid": uuid,
        }
        with open(self.user_data_file, "w", encoding="utf-8") as f:
            json.dump(player_data, f, ensure_ascii=False, indent=4)
    
    @filter.regex(r"^(?:获取战绩|战绩)\s*(.+)")
    async def fetch_match_stats(self, event: AstrMessageEvent):
        """响应用户获取战绩请求，读取存储的玩家数据并获取战绩信息"""
        full_text = event.message_str.strip()
        username = re.match(r"^(?:获取战绩|战绩)\s*(.+)", full_text)
        with open(self.user_data_file, "r", encoding="utf-8") as f:
            player_data = json.load(f)
        if username not in player_data:
            yield event.plain_result(f"用户 {username} 未添加任何玩家数据，请先添加玩家。")
            return
        player_info = player_data[username]
        uuid = player_info.get("uuid")
        async with aiohttp.ClientSession() as session:
            match_id = await self.get_match_id(session, uuid)
            if not match_id:
                yield event.plain_result(f"未找到玩家 {player_info.get('name')} 的最近比赛信息。")
                return
            match_stats = await self.get_match_stats(session, match_id)
            if not match_stats:
                yield event.plain_result(f"未能获取比赛 {match_id} 的详细数据。")
                return
            match_stats_json = await self.process_json(match_stats)
            yield event.plain_result(f"玩家 {player_info.get('name')} 的最近一场比赛中：{match_stats_json}")

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
