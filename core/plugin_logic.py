import json
import re
import urllib.parse
from typing import Union

import aiohttp
from tenacity import retry, stop_after_attempt, wait_fixed

from astrbot.api.star import Context
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from astrbot.core.message.components import ComponentType
from ..models.player_data import PlayerDataRequest
from ..models.match_data import PlayerStats, MatchData


class CstatsCheckPluginLogic:
    def __init__(self, session, data_dir, prompt: str):
        self.data_dir = data_dir
        self.user_data_file = self.data_dir / "user_data.json"
        self._session = session
        self.prompt = prompt

    async def handle_player_data_request_bind(
        self, event: AstrMessageEvent
    ) -> PlayerDataRequest:
        """
        处理bind指令的请求
        Args:
            event: AstrMessageEvent
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

        full_text = event.message_str.strip()
        match = re.match(r"^(?:添加用户|绑定用户|添加|绑定|bind)\s*(.+)", full_text)
        if match is not None:
            playername = match.groups()[0].strip()

        if playername is None:
            error_msg = "玩家名称未成功识别，请检查命令输入"
        else:
            error_msg = await self._user_is_added(username, playername)

        return PlayerDataRequest(
            message_str=message_str,
            user_name=username,
            domain=domain,
            qq_id=qq_id,
            uuid=uuid,
            player_name=playername,
            error_msg=error_msg,
        )

    async def handle_player_data_request_match(
        self, event: AstrMessageEvent
    ) -> tuple[PlayerDataRequest, int]:
        """
        处理match指令的请求
        Args:
            event: AstrMessageEvent
        Returns:
            PlayerDataRequest: 包含所有提取参数的数据类实例
            int: 查询比赛场次
        """
        message_str = event.message_str
        qq_id = event.get_sender_id()
        username = event.get_sender_name()
        domain = None
        playername = None
        uuid = None
        error_msg = None

        match_round = 1

        msg_chain = event.get_messages()
        if len(msg_chain) == 1:
            match = re.search(r"\b(\d+)\b", msg_chain[0].toString())
            if match:
                match_round = int(match.group(1))
            qq_id = event.get_sender_id()
        else:
            for comp in msg_chain[1:]:
                if comp.type == ComponentType.At:
                    com_dic = comp.toDict()
                    qq_id = com_dic.get("data", {}).get("qq")
                if comp.type == ComponentType.Plain:
                    match = re.search(r"\b(\d+)\b", comp.toString())
                    if match:
                        match_round = int(match.group(1))
        with open(self.user_data_file, "r", encoding="utf-8") as f:
            user_data = json.load(f)
        if qq_id not in user_data:
            error_msg = f"用户 {qq_id} 未添加数据，请先添加游戏ID"
        else:
            playername = user_data[qq_id]["name"]
        player_info = user_data[qq_id]
        # 更新 request_data.uuid
        uuid = player_info.get("uuid")

        return PlayerDataRequest(
            message_str=message_str,
            user_name=username,
            domain=domain,
            qq_id=qq_id,
            uuid=uuid,
            player_name=playername,
            error_msg=error_msg,
        ), match_round

    async def call_llm_to_generate_evaluation(
        self, event: AstrMessageEvent, context: Context, stats_text: str
    ) -> Union[str, None]:
        "调用llm对战绩生成评价"
        prov = context.get_using_provider(umo=event.unified_msg_origin)
        if prov:
            llm_resp = await prov.text_chat(
                prompt=f"{stats_text}",
                context=[
                    {
                        "role": "user",
                        "content": "5eplayer 薛定谔的哥本哈根 最近一场比赛战绩：\nMap: 炙热沙城2 \n比赛结果: 失败 \nRating: 0.91  \nADR: 53.16 \nElo变化: 12.78",
                    },
                    {"role": "cs战绩短评官", "content": "评价为这把睡了，但睡得不深"},
                    {
                        "role": "user",
                        "content": "5eplayer Mr_Bip 最近一场比赛战绩：\nMap: 炙热沙城2 \n比赛结果: 失败 \nRating: 1.59  \nADR: 121.05 \nElo变化: 27.71",
                    },
                    {"role": "cs战绩短评官", "content": "评价为燃成灰了都带不动四个fw"},
                    {
                        "role": "user",
                        "content": "5eplayer 薛定谔的哥本哈根 最近一场比赛战绩: Map: 炙热沙城2 比赛结果: 胜利  Elo变化: 12.78 rating: 0.91 adr: 53.16 kill: 11    death: 10 爆头率: 27.27%",
                    },
                    {"role": "cs战绩短评官", "content": "评价为躺赢局，数据比体温还低"},
                    {
                        "role": "user",
                        "content": "5eplayer 薛定谔的哥本哈根 的上上局比赛战绩: Map: 炙热沙城2 比赛结果: 胜利  Elo变化: -14.88 rating: 0.71 adr: 76.94 kill: 10    death: 15 爆头率: 50.00%",
                    },
                    {
                        "role": "cs战绩短评官",
                        "content": "评价为薛定谔的哥本哈出，裤子里全是尿，没有一滴汗",
                    },
                ],
                system_prompt="你需要对上面的cs战绩结合比赛结果和个人表现进行一个简短的评价，不超过二十个字，整体风格是黑色幽默那种，rating 和 adr 是这局表现的重要参考因素，rating 和 adr 很高(1.2raing以上或者90ADR以上，越高越强，夸得越凶)但是输了可以用悲情英雄、尽力局、拉满了、燃成灰了、一绿带四红来形容，打得好赢了可以用明星哥、个人英雄主义、大哥、数值拉满了、带飞等来形容，打得菜(0.8rating以下或者50ADR以下，越低越菜，骂得越狠)可以用美美隐身、这把睡了、摊子、不像人类、尿完了、裤子里全是尿，没有一滴汗、fvv、bot、玩家名称中选一部分+出(比如玩家名称叫玩机器，就可以称为 玩出，请注意要根据玩家名称来，不要忽视玩家名称直接套用玩出) 作为称呼来形容，如果战绩一般就正常评价吧，但是请注意，不要只是简单地采用上面的短语，要在上面的短语基础上增添内容，可以经常在句首加上“评价为”，但是不用在后面跟上冒号这类标点，菜的时候就刻薄一点，强的时候用不夸张的话夸，可以向上下文中的cs战绩短评官的评价进行学习，注意最后的评价内容要善于变化，不要说来说去都是那几句话，还要注意 5eplayer 只是展示平台，和玩家名称无关，评价的时候不要出现5eplayer",
            )
            logger.info(llm_resp)
            return llm_resp.completion_text
        return None

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
            try:
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"获取domain失败：HTTP {resp.status}，错误：{e}")
                request_data.error_msg = (
                    f"获取domain失败：HTTP {resp.status}，错误：{e}"
                )
                return
            data = await resp.json()

            users = data.get("data", {}).get("user", {}).get("list", [])
            for u in users:
                if u.get("username") == request_data.player_name:
                    request_data.domain = u.get("domain")
                    if not request_data.domain:
                        logger.error("获取domain失败，服务器返回数据错误")
                        request_data.error_msg = "获取domain失败，服务器返回数据错误"
                    return
            return

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
            "Origin": "https://arena-next.5eplaycdn.com",
            "Referer": "https://arena-next.5eplaycdn.com/",
        }
        post_data = {"trans": {"domain": request_data.domain}}

        async with session.post(post_url, json=post_data, headers=post_headers) as resp:
            try:
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"获取uuid失败：HTTP {resp.status}，错误：{e}")
                request_data.error_msg = f"获取uuid失败：HTTP {resp.status}，错误：{e}"
                return
            data = await resp.json()
            uuid = data.get("data", {}).get("uuid")
            if not uuid:
                logger.error("获取uuid失败，服务器返回数据错误")
                request_data.error_msg = "获取uuid失败，服务器返回数据错误"
            else:
                request_data.uuid = uuid
            return

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))  # 重试3次，每次间隔2秒
    async def get_match_id(
        self,
        session: aiohttp.ClientSession,
        request_data: PlayerDataRequest,
        match_round,
    ):
        """根据 uuid 获取最近一把比赛的 match_id"""
        get_url = f"https://gate.5eplay.com/crane/http/api/data/player_match?uuid={request_data.uuid}"
        get_headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0",
            "Accept": "*/*",
            "Accept-Language": "zh-cn",
            "Authorization": "",
            "Host": "gate.5eplay.com",
            "Origin": "https://arena-next.5eplaycdn.com",
            "Referer": "https://arena-next.5eplaycdn.com/",
            "TE": "trailers",
        }

        async with session.get(get_url, headers=get_headers) as resp:
            try:
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"获取match_id失败：HTTP {resp.status}，错误：{e}")
                request_data.error_msg = (
                    f"获取match_id失败：HTTP {resp.status}，错误：{e}"
                )
                return
            data = await resp.json()
            match_list = data.get("data", {}).get("match_data", [])
            if match_list:
                match_id = match_list[match_round - 1].get("match_id")
                if not match_id:
                    logger.error(
                        f"获取玩家 {request_data.player_name} 的{match_round * '上'}比赛的match_id失败"
                    )
                    request_data.error_msg = f"获取玩家 {request_data.player_name} 的{match_round * '上'}比赛的数据失败，请稍后重试"
                return match_id
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))  # 重试3次，每次间隔1秒
    async def get_match_stats(
        self, session: aiohttp.ClientSession, match_id, request_data: PlayerDataRequest
    ):
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
            try:
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"获取uuid失败：HTTP {resp.status}，错误：{e}")
                request_data.error_msg = f"获取uuid失败：HTTP {resp.status}，错误：{e}"
                return
            data = await resp.json()
            return data.get("data", {})

    async def process_json(
        self,
        json_data,
        match_round,
        player_send,
    ) -> MatchData:
        """处理比赛数据，从json数据中提取所需参数"""
        # 先存一份完整 json 数据留作备份
        # with open(self.data_dir / f"match_{match_id}.json", "w", encoding="utf-8") as f:
        #     json.dump(json_data, f, ensure_ascii=False, indent=4)
        # 这里根据实际的 json 结构提取所需信息
        error_msg = None
        basic_info = json_data.get("main", {})
        match_map = basic_info["map_desc"]
        start_time = basic_info["start_time"]
        end_time = basic_info["end_time"]
        mvp_uid = basic_info["mvp_uid"]
        group_1 = json_data.get("group_1", [])
        group_2 = json_data.get("group_2", [])
        players_stats = group_1 + group_2
        players_to_find = player_send
        match_data = MatchData(
            match_round=match_round,
            map=match_map,
            start_time=start_time,
            end_time=end_time,
            player_stats={},
            mvp_uid=mvp_uid,
            error_msg=error_msg,
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
        return match_data

    async def handle_to_llm_text(
        self, match_data: MatchData, player_send: Union[str, None]
    ) -> str:
        "生成llm将要进行评价的战绩text"
        player_stats = match_data.player_stats[f"{player_send}"]
        if player_stats.win == 1:
            match_result = "胜利"
        else:
            match_result = "失败"
        text = f"5eplayer {player_stats.playername} 的{'上' * match_data.match_round}把比赛战绩:\n比赛时间: {match_data.start_datetime}   比赛时长: {match_data.duration}min\nMap: {match_data.map} 比赛结果: {match_result} \nElo变化: {player_stats.elo_change}\nkd: {player_stats.kill}-{player_stats.death}\nrating: {player_stats.rating}\nadr: {player_stats.adr}\n爆头率: {player_stats.headshot_rate * 100:.2f}% "
        return text

    @staticmethod
    def _extract_player_data(json_data, player) -> PlayerStats:
        """提取比赛中玩家数据，返回PlayerStats"""
        uuid = json_data.get("user_info", {}).get("user_data", {}).get("uuid")
        uid = json_data.get("user_info", {}).get("user_data", {}).get("uid")
        is_win = int(json_data.get("fight", {}).get("is_win"))
        elo_change = float(json_data.get("sts", {}).get("change_elo", 0))
        rating = float(json_data.get("fight", {}).get("rating2"))
        adr = float(json_data.get("fight", {}).get("adr"))
        rws = float(json_data.get("fight", {}).get("rws"))
        kill = int(json_data.get("fight", {}).get("kill"))
        death = int(json_data.get("fight", {}).get("death"))
        if kill == 0:
            headshot_rate = 0
        else:
            headshot_rate: float = (
                int(json_data.get("fight", {}).get("headshot")) / kill
            )
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

    async def _user_is_added(self, username: str, playername: str) -> Union[str, None]:
        """检查用户是否已添加玩家数据"""
        error_msg = None
        if self.user_data_file.exists():
            with open(self.user_data_file, "r", encoding="utf-8") as f:
                player_data = json.load(f)
            if username in player_data and player_data[username]["name"] == playername:
                error_msg = f"用户 {username} 已添加玩家 {playername} 的数据。"
        return error_msg
