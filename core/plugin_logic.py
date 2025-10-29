import json
import urllib.parse
from typing import Union

import aiohttp
from tenacity import retry, stop_after_attempt, wait_fixed

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..models.player_data import PlayerDataRequest
from ..models.match_data import PlayerStats, MatchData


class CstatsCheckPluginLogic:
    def __init__(self, session, data_dir, prompt: str):
        self.data_dir = data_dir
        self.user_data_file = self.data_dir / "user_data.json"
        self._session = session
        self.prompt = prompt

    def get_session_channel_id(self, event: AstrMessageEvent) -> str:
        """根据事件类型获取会话渠道ID"""
        if not event.is_private_chat():
            return event.get_group_id()
        return event.get_sender_id()

    async def _resolve_5e_name(
        self, ea_name_input: Union[str, None], qq_id: str
    ) -> tuple[Union[str, None], Union[str, None], Union[str, None]]:
        """
        解析EA账号名，获取默认值。
        Returns:
            tuple: (ea_name, error_message)
        """
        ea_name = ea_name_input
        uuid = ""
        error_msg = None

        # if ea_name is None:
        #     bind_data = await self.db_service.query_bind_user(qq_id)
        #     if bind_data is None:
        #         error_msg = "请先使用bind [ea_name]绑定"
        #     else:
        #         ea_name = bind_data.get("ea_name")
        #         uuid = bind_data.get("ea_id",None)
        return ea_name, uuid, error_msg

    async def handle_player_data_request(
        self, event: AstrMessageEvent, str_to_remove_list: list
    ) -> PlayerDataRequest:
        """
        从消息中提取参数
        Args:
            event: AstrMessageEvent
            str_to_remove_list: 去除指令
        Returns:
            PlayerDataRequest: 包含所有提取参数的数据类实例
        """
        message_str = event.message_str
        qq_id = event.get_sender_id()
        username = event.get_sender_name()
        domain = None
        playername = None
        uuid = None
        error_msg = None

        try:
            #     # 解析命令
            playername = await self._parse_input_regex(str_to_remove_list, message_str)
            #     # 由于共用解析方法所以这里赋个值
            #     if str_to_remove_list == ["servers", "服务器"]:
            #         server_name = ea_name
            # 处理EA账号名
            if not playername and not uuid:
                playername, uuid, ea_name_error = await self._resolve_5e_name(
                    playername, qq_id
                )
                if ea_name_error:
                    error_msg = ea_name_error
                    raise ValueError(error_msg)  # 抛出异常以便被捕获

        except Exception as e:
            error_msg = str(e)

        return PlayerDataRequest(
            message_str=message_str,
            user_name=username,
            domain=domain,
            qq_id=qq_id,
            uuid=uuid,
            player_name=playername,
            error_msg=error_msg,
        )

    def _get_playername(
        self, playername_input: Union[str, None], qq_id: str
    ) -> tuple[Union[str, None], Union[str, None], Union[str, None]]:
        """获取玩家名称，优先使用输入的名称，其次使用QQ绑定名称"""
        playername = playername_input
        uuid = ""
        error_msg = None

        # if playername is None:
        #     bind_data = await self.db_service.query_bind_user(qq_id)
        return playername, uuid, error_msg

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))  # 重试3次，每次间隔2秒
    async def get_domain(
        self, session: aiohttp.ClientSession, request_data: PlayerDataRequest
    ):
        """根据用户输入的 playername 获取 domain"""
        # 处理可能为 None 的 playername，并对其进行 bytes 编码后使用 quote_from_bytes（避免类型检查报错）
        playername = request_data.player_name or ""
        playername_bytes = playername.encode("utf-8")
        playername_encoded = urllib.parse.quote_from_bytes(playername_bytes)
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
        }
        url = "https://arena.5eplay.com/api/search/player/1/16"
        params = {"keywords": request_data.player_name}

        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status != 200:
                print(f"获取domain失败：HTTP {resp.status}")
                return None
            data = await resp.json()

            users = data.get("data", {}).get("user", {}).get("list", [])
            for u in users:
                if u.get("username") == request_data.player_name:
                    return u.get("domain")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))  # 重试3次，每次间隔2秒
    async def get_uuid(
        self, session: aiohttp.ClientSession, request_data: PlayerDataRequest
    ):
        """根据 domain 获取 uuid"""
        post_url = (
            "https://gate.5eplay.com/userinterface/http/v1/userinterface/idTransfer"
        )
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
        post_data = {"trans": {"domain": request_data.domain}}

        async with session.post(post_url, json=post_data, headers=post_headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
            uuid = data.get("data", {}).get("uuid")
            return uuid

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))  # 重试3次，每次间隔2秒
    async def get_match_id(
        self, session: aiohttp.ClientSession, request_data: PlayerDataRequest
    ):
        """根据 uuid 获取最近一把比赛的 match_id"""
        get_url = f"https://gate.5eplay.com/crane/http/api/data/player_match?uuid={request_data.uuid}"
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

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))  # 重试3次，每次间隔1秒
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

    async def process_json(
        self,
        json_data,
        match_id,
        player_send,
        teammate_of_send: list[str] | None = None,
    ) -> MatchData:
        """处理比赛数据，提取并格式化战绩信息"""
        # 先存一份完整 json 数据留作备份
        with open(self.data_dir / f"match_{match_id}.json", "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=4)
        # 这里根据实际的 json 结构提取所需信息
        basic_info = json_data.get("main", {})
        match_map = basic_info["map_desc"]
        start_time = basic_info["start_time"]
        end_time = basic_info["end_time"]
        mvp_uid = basic_info["mvp_uid"]
        group_1 = json_data.get("group_1", [])
        group_2 = json_data.get("group_2", [])
        players_stats = group_1 + group_2
        players_to_find = [player_send] + (teammate_of_send if teammate_of_send else [])
        match_data = MatchData(
            map=match_map,
            start_time=start_time,
            end_time=end_time,
            player_stats={},
            mvp_uid=mvp_uid,
        )
        for player_stats in players_stats:
            if (
                player_stats.get("user_info", {}).get("user_data", {}).get("username")
                in players_to_find
            ):
                player_to_find = (
                    player_stats.get("user_info", {})
                    .get("user_data", {})
                    .get("username")
                )
                player_data = self._extract_player_data(player_stats, player_to_find)
                match_data.player_stats[player_data.playername] = player_data
        # if len(players) == 1:
        #     noobname, noobdata = "", {}
        # else:
        #     noobname, noobdata = min(player_data.items(), key=lambda x: x[1]["rating"])

        return match_data

    async def handle_to_llm_text(self, match_data: MatchData, player_send: str) -> str:
        # match_map, player_send_data, noobname, noobdata = await self.plugin_logic.process_json(match_stats, match_id, player_send, teammate_of_send)
        # player_send_text = f"5eplayer {player_send} 最近一场比赛战绩：\nMap: {match_map}\n比赛结果: {player_send_data['is_win']}\nRating: {player_send_data['rating']} \nADR: {player_send_data['adr']}\nElo变化: {player_send_data['change_elo']}\n"
        # if noobname == "":
        #     noob_text = "你一个人偷偷玩的，真厉害"
        # elif noobname == player_send:
        #     noob_text = "你就是最菜的，怎么敢查战绩的"
        # else:
        #     noob_text = f"本场菜比是 {noobname}，打出了 {noobdata['rating']} 超高rating，这是人类啊"
        player_stats = match_data.player_stats["playersend"]
        if player_stats.win:
            match_result = "胜利"
        else:
            match_result = "失败"
        text = f"5eplayer {player_stats.playername} 最近一场比赛战绩:\n Map: {match_data.map} 比赛结果: {match_result} \nElo变化:{player_stats.elo_change}\n rating: {player_stats.rating}\nadr: {player_stats.adr}\nkill:{player_stats.kill}  death:{player_stats.death}\n爆头率:{player_stats.headshot_rate} "
        return text


    @staticmethod
    def _extract_player_data(json_data, player) -> PlayerStats:
        """提取比赛中玩家数据，返回PlayerStats"""
        uuid = json_data.get("user_info", {}).get("user_data", {}).get("uuid")
        uid = json_data.get("user_info", {}).get("user_data", {}).get("uid")
        is_win = json_data.get("fight", {}).get("is_win")
        elo_change = json_data.get("sts", {}).get("change_elo", 0)
        rating = json_data.get("fight", {}).get("rating2")
        adr = json_data.get("fight", {}).get("adr")
        rws = json_data.get("fight", {}).get("rws")
        kill = json_data.get("fight", {}).get("kill")
        death = json_data.get("fight", {}).get("death")
        if kill == 0:
            headshot_rate = 0
        else:
            headshot_rate: float = json_data.get("fight", {}).get("headshot") / kill
        return PlayerStats(
            playername=player,
            uuid=uuid,
            uid=uid,
            win=is_win,
            elo_change=elo_change,
            rating=rating,
            adr=adr,
            rws=rws,
            kill=kill,
            death=death,
            headshot_rate=headshot_rate,
        )

    async def user_is_added(self, username: str, playername: str) -> bool:
        """检查用户是否已添加玩家数据"""
        if self.user_data_file.exists():
            with open(self.user_data_file, "r", encoding="utf-8") as f:
                player_data = json.load(f)
            return (
                username in player_data and player_data[username]["name"] == playername
            )
        return False

    @staticmethod
    async def _parse_input_regex(
        str_to_remove_list: list[str],
        base_string: str,
    ):
        """私有方法：从base_string中移除str_to_remove_list并去空格，然后根据正则取出参数
        Args:
            str_to_remove_list: 需要移除的子串list
            base_string: 原始字符串
        Returns:
            处理后的字符串
        """
        # 移除目标子串和空格
        for str_to_remove in str_to_remove_list:
            base_string = base_string.replace(str_to_remove, "")
        clean_str = base_string.replace(" ", "")
        # 用正则提取输入的参数
        name = clean_str.strip()
        # if pattern is not None:
        #     match = pattern.match(clean_str.strip())
        #     if not match:
        #         raise ValueError("格式错误，正确格式：[用户名][,game=游戏名]")
        #     name = match.group(1) or None
        # else:
        #     name = clean_str.strip()
        return name
