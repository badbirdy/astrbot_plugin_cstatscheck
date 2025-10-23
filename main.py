import re
import json
import asyncio
import urllib.parse
import aiohttp
from tenacity import retry, stop_after_attempt, wait_fixed
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
#todo: 增加错误处理和日志记录
#todo: 优化数据存储结构，支持多个玩家数据，解决self数据的覆盖问题
#todo：增加战绩数据的格式化输出，而不是仅仅输出地图名称
#todo：增加命令帮助信息，方便用户使用
#todo：增加单元测试
#todo：引入 tenacity 库以处理网络请求的重试和超时

@register("cstatcheck", "badbirdy", "一个简单的 cs 战绩查询插件", "1.0.0")
class Player(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir()
        self.user_data_file = self.data_dir / "user_data.json"
        self.username: str = "" #  发送指令的用户名称
        self.playername: str = "" # user 对应的玩家名称
        self.domain: str = "" # 仅仅用于查询 playername 对应的 uuid
        self.uuid: str = "" # 用于查询战绩

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        #  确保数据目录存在
        self.data_dir.mkdir(exist_ok=True)
        # 如果用户数据文件不存在，则创建一个空的 JSON 文件
        if not self.user_data_file.exists():
            with open(self.user_data_file, "w", encoding="utf-8") as f:
                json.dump({}, f)

    # # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    # @filter.command("helloworld")
    # async def helloworld(self, event: AstrMessageEvent):
    #     """这是一个 hello world 指令""" # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
    #     user_name = event.get_sender_name()
    #     message_str = event.message_str # 用户发的纯文本消息字符串
    #     message_chain = event.get_messages() # 用户所发的消息的消息链 # from astrbot.api.message_components import *
    #     logger.info(message_chain)
    #     yield event.plain_result(f"Hello, {user_name}, 你发了 {message_str}!") # 发送一条纯文本消息

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1)) # 重试3次，每次间隔2秒
    async def get_domain(self, session: aiohttp.ClientSession):
        """根据用户输入的 playername 获取 domain"""
        # URL encode 用户名
        playername_encoded = urllib.parse.quote(self.playername)
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
        params = {"keywords": self.playername}

        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status != 200:
                print(f"获取domain失败：HTTP {resp.status}")
                return None
            data = await resp.json()

            users = data.get("data", {}).get("user", {}).get("list", [])
            for u in users:
                if u.get("username") == self.playername:
                    return u.get("domain")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1)) # 重试3次，每次间隔2秒
    async def get_uuid(self, session: aiohttp.ClientSession):
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
                "domain": self.domain
            }
        }

        async with session.post(post_url, json=post_data, headers=post_headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
            uuid = data.get("data", {}).get("uuid")
            return uuid

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1)) # 重试3次，每次间隔2秒
    async def get_match_id(self, session: aiohttp.ClientSession):
        """根据 uuid 获取最近一把比赛的 match_id"""
        get_url = f"https://gate.5eplay.com/crane/http/api/data/player_match?uuid={self.uuid}"
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

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1)) # 重试3次，每次间隔2秒
    async def get_match_stats(self, session: aiohttp.ClientSession, match_id):
        """根据 match_id 获取比赛数据"""
        get_url = f"https://gate.5eplay.com/crane/http/api/data/match/{match_id}"
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

    async def process_json(self, json_data, match_id, player_send):
        """处理比赛数据，提取并格式化战绩信息"""
        # 先存一份完整 json 数据留作备份
        with open(self.data_dir / f"match_{match_id}.json", "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=4)
        # 这里根据实际的 json 结构提取所需信息
        basic_info = json_data.get("main", {})
        match_map = basic_info["map_desc"]
        group_1 = json_data.get("group_1", [])
        group_2 = json_data.get("group_2", [])
        players = group_1 + group_2
        player_data = {}
        for player in players:
            adr = player.get("fight", {}).get("adr")
            rating = player.get("fight", {}).get("rating2")
            change_elo = player.get("sts", {}).get("change_elo")
            playername = player.get("user_info", {}).get("user_data", {}).get("username")
            # 创建字典数组存储信息
            player_data[playername] = {
                "adr": adr,
                "rating": rating,
                "change_elo": change_elo
            }
            # 存进 json 文件查看
            with open(self.data_dir / f"match_{match_id}_players.json", "w", encoding="utf-8") as f:
                json.dump(player_data, f, ensure_ascii=False, indent=4)
        # return map, player_data_list
        # 先测试性地简单返回一个 map
        return f"\n地图: {match_map}\nRating：{player_data[player_send]['rating']}\nADR：{player_data[player_send]['adr']}"

    @filter.regex(r"^(?:添加用户|用户|添加玩家|玩家)\s*(.+)")
    async def add_player_data(self, event: AstrMessageEvent):
        """响应用户添加玩家请求，并进行将玩家数据进行存储"""

        full_text = event.message_str.strip()
        match = re.match(r"^(?:添加用户|用户|添加玩家|玩家)\s*(.+)", full_text)
        self.playername = match.groups()[0].strip()
        self.username = event.get_sender_name()
        domain = None
        uuid = None

        if await self.user_is_added(self.username, self.playername):
            yield event.plain_result(f"用户 {self.username} 已添加玩家 {self.playername} 的数据。")
            return
        async with aiohttp.ClientSession() as session:
            self.domain = await self.get_domain(session)
            if not self.domain:
                yield event.plain_result(f"获取玩家 {self.playername} 的 domain 信息失败，请稍候重试")
                return
            # else:
            #     yield event.plain_result(f"成功获取到 domain: {self.domain}")
            self.uuid = await self.get_uuid(session)
            if not self.uuid:
                yield event.plain_result(f"获取玩家 {self.playername} 的 uuid 信息失败，请稍后重试")
                return
            # else:
            #     yield event.plain_result(f"成功获取到 uuid: {self.uuid}")

        # 存储玩家信息到 JSON 文件
        player_data = {}
        if self.user_data_file.exists():
            with open(self.user_data_file, "r", encoding="utf-8") as f:
                player_data = json.load(f)
        player_data[self.username] = {
            "name": self.playername,
            "domain": self.domain,
            "uuid": self.uuid,
        }
        yield event.plain_result(f"成功添加用户 {self.username} 对应的玩家 {self.playername} 数据。")
        with open(self.user_data_file, "w", encoding="utf-8") as f:
            json.dump(player_data, f, ensure_ascii=False, indent=4)
    
    @filter.regex(r"^(?:获取战绩|战绩)\s*(.*)")
    async def fetch_match_stats(self, event: AstrMessageEvent):
        """响应用户获取战绩请求，读取存储的玩家数据并获取战绩信息"""
        full_text = event.message_str.strip()
        match = re.match(r"^(?:获取战绩|战绩)\s*@?([^\(]+)", full_text)
        if match is None:
            self.username = event.get_sender_name()
        else:
            self.username = match.groups()[0].strip()
        with open(self.user_data_file, "r", encoding="utf-8") as f:
            player_data = json.load(f)
        if self.username not in player_data:
            yield event.plain_result(f"用户 {self.username} 未添加数据，请先添加游戏ID")
            return
        else:
            player_send = player_data[self.username]["name"]
        player_info = player_data[self.username]
        # 更新 self.uuid
        self.uuid = player_info.get("uuid")
        async with aiohttp.ClientSession() as session:
            match_id = await self.get_match_id(session)
            if not match_id:
                yield event.plain_result(f"未找到玩家 {player_info.get('name')} 的最近比赛信息。")
                return
            # else:
            #     yield event.plain_result(f"玩家 {player_info.get('name')} 最近的一场比赛 ID: {match_id}")
            match_stats = await self.get_match_stats(session, match_id)
            if not match_stats:
                yield event.plain_result(f"未能获取比赛 {match_id} 的详细数据。")
                return
            # else:
            #     yield event.plain_result(f"成功获取比赛 {match_id} 的详细数据。")
            match_stats_json = await self.process_json(match_stats, match_id, player_send)
            yield event.plain_result(f"{player_info.get('name')} 的最近一场比赛中：{match_stats_json}")

    async def user_is_added(self, username: str, playername: str) -> bool:
        """检查用户是否已添加玩家数据"""
        if self.user_data_file.exists():
            with open(self.user_data_file, "r", encoding="utf-8") as f:
                player_data = json.load(f)
            return username in player_data and player_data[username]["name"] == playername
        return False

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""