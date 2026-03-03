import urllib.parse

import aiohttp
from tenacity import retry, stop_after_attempt, wait_fixed

from astrbot.api import logger

from ...models.match_data import MatchData, PlayerStats
from ...models.player_data import PlayerDataRequest


class FiveEPlatformLogic:
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def get_domain(
        self, session: aiohttp.ClientSession, request_data: PlayerDataRequest
    ):
        playername = request_data.player_name or ""
        playername_encoded = urllib.parse.quote_from_bytes(playername.encode("utf-8"))
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
            except Exception as exc:
                logger.error(f"获取domain失败：HTTP {resp.status}，错误：{exc}")
                request_data.error_msg = "绑定用户失败，请检查网络后重试"
                return
            data = await resp.json()
            users = data.get("data", {}).get("user", {}).get("list", [])
            for item in users:
                if item.get("username") == request_data.player_name:
                    request_data.domain = item.get("domain", "")
            if not request_data.domain:
                logger.error("获取domain失败，请检查用户ID是否输入正确")
                request_data.error_msg = "绑定用户失败，请检查用户ID是否输入正确"

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def get_uuid(
        self, session: aiohttp.ClientSession, request_data: PlayerDataRequest
    ):
        url = "https://gate.5eplay.com/userinterface/http/v1/userinterface/idTransfer"
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0",
            "Accept": "*/*",
            "Accept-Language": "zh-cn",
            "Content-Type": "application/json",
            "Origin": "https://arena-next.5eplaycdn.com",
            "Referer": "https://arena-next.5eplaycdn.com/",
        }
        payload = {"trans": {"domain": request_data.domain}}
        async with session.post(url, json=payload, headers=headers) as resp:
            try:
                resp.raise_for_status()
            except Exception as exc:
                logger.error(f"获取uuid失败：HTTP {resp.status}，错误：{exc}")
                request_data.error_msg = "绑定用户失败，请检查网络后重试"
                return
            data = await resp.json()
            uuid = data.get("data", {}).get("uuid", "")
            if not uuid:
                logger.error("获取uuid失败，服务器返回数据错误")
                request_data.error_msg = "绑定用户失败，请检查用户ID是否输入正确"
                return
            request_data.uuid = uuid

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def get_match_id(
        self,
        session: aiohttp.ClientSession,
        request_data: PlayerDataRequest,
        match_round: int,
    ):
        url = f"https://gate.5eplay.com/crane/http/api/data/player_match?uuid={request_data.uuid}"
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0",
            "Accept": "*/*",
            "Accept-Language": "zh-cn",
            "Authorization": "",
            "Host": "gate.5eplay.com",
            "Origin": "https://arena-next.5eplaycdn.com",
            "Referer": "https://arena-next.5eplaycdn.com/",
            "TE": "trailers",
        }
        async with session.get(url, headers=headers) as resp:
            try:
                resp.raise_for_status()
            except Exception as exc:
                logger.error(f"获取match_id失败：HTTP {resp.status}，错误：{exc}")
                request_data.error_msg = "查询比赛数据失败，请检查网络后重试"
                return None
            data = await resp.json()
            match_list = data.get("data", {}).get("match_data", [])
            if not match_list or match_round <= 0 or match_round > len(match_list):
                request_data.error_msg = f"获取玩家 {request_data.player_name} 的{match_round * '上'}比赛的数据失败，请稍后重试"
                return None
            match_id = match_list[match_round - 1].get("match_id", "")
            if not match_id:
                request_data.error_msg = f"获取玩家 {request_data.player_name} 的{match_round * '上'}比赛的数据失败，请稍后重试"
                return None
            return match_id

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def get_match_stats(
        self,
        session: aiohttp.ClientSession,
        match_id: str,
        request_data: PlayerDataRequest,
    ):
        url = f"https://gate.5eplay.com/crane/http/api/data/match/{match_id}"
        headers = {
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
        async with session.get(url, headers=headers) as resp:
            try:
                resp.raise_for_status()
            except Exception as exc:
                logger.error(f"获取match_stats失败：HTTP {resp.status}，错误：{exc}")
                request_data.error_msg = "获取比赛数据失败，请检查网络后重试"
                return None
            data = await resp.json()
            payload = data.get("data", {})
            if not payload:
                request_data.error_msg = (
                    f"获取比赛的详细数据失败 (match_id={match_id}) "
                )
                return None
            return payload

    async def process_json(
        self,
        json_data,
        match_round: int,
        player_send: str,
        player_uuid: str | None = None,
    ) -> MatchData:
        _ = player_uuid
        basic_info = json_data.get("main", {})
        match_data = MatchData(
            match_round=match_round,
            map=basic_info.get("map_desc", "未知地图"),
            start_time=basic_info.get("start_time", 0),
            end_time=basic_info.get("end_time", 0),
            player_stats={},
            teammate_players=[],
            opponent_players=[],
            mvp_uid=basic_info.get("mvp_uid", ""),
            error_msg=None,
        )
        group_1 = json_data.get("group_1", [])
        group_2 = json_data.get("group_2", [])
        target_group, opponent_group = self._resolve_groups_by_player_name(
            group_1, group_2, player_send or ""
        )
        if target_group is None or opponent_group is None:
            match_data.error_msg = f"未在比赛数据中找到玩家 {player_send}"
            return match_data

        for player_stats in target_group:
            player_name = (
                player_stats.get("user_info", {})
                .get("user_data", {})
                .get("username", "")
            )
            if player_name == player_send:
                pdata = self._extract_player_data(player_stats, player_name)
                match_data.player_stats[pdata.playername] = pdata
                break

        if player_send not in match_data.player_stats:
            match_data.error_msg = f"未在比赛数据中找到玩家 {player_send}"
            return match_data

        for player_stats in target_group:
            player_name = (
                player_stats.get("user_info", {})
                .get("user_data", {})
                .get("username", "")
            )
            if player_name != player_send:
                match_data.teammate_players.append(
                    self._extract_player_data(player_stats, player_name)
                )

        for player_stats in opponent_group:
            player_name = (
                player_stats.get("user_info", {})
                .get("user_data", {})
                .get("username", "")
            )
            match_data.opponent_players.append(
                self._extract_player_data(player_stats, player_name)
            )

        return match_data

    async def get_premade_summary(
        self,
        user_data,
        json_data,
        player_send: str | None,
        player_uuid: str | None = None,
    ) -> dict:
        _ = player_uuid
        default_result = {
            "teammate_names": [],
            "worst_player_qq": None,
            "worst_player_name": "",
            "target_is_worst": False,
        }
        uuid_to_bound_player = {}
        for qq_id, player_info in user_data.items():
            platform_data = player_info.get("platform_data", {}).get("5e")
            if platform_data:
                bound_player_uuid = platform_data.get("uuid", "")
                player_name = platform_data.get("name", "")
            else:
                bound_player_uuid = player_info.get("uuid", "")
                player_name = player_info.get("name", "")
            if bound_player_uuid:
                uuid_to_bound_player[bound_player_uuid] = {
                    "qq_id": qq_id,
                    "name": player_name,
                }

        if not uuid_to_bound_player:
            return default_result

        target_name = player_send or ""
        group_1 = json_data.get("group_1", [])
        group_2 = json_data.get("group_2", [])
        target_group, _ = self._resolve_groups_by_player_name(
            group_1, group_2, target_name
        )
        if target_group is None:
            return default_result

        bound_team_players = []
        for player_raw in target_group:
            player_name = (
                player_raw.get("user_info", {}).get("user_data", {}).get("username", "")
            )
            player_uuid = (
                player_raw.get("user_info", {}).get("user_data", {}).get("uuid", "")
            )
            if not player_uuid or player_uuid not in uuid_to_bound_player:
                continue
            bound_info = uuid_to_bound_player[player_uuid]
            bound_team_players.append(
                {
                    "name": player_name,
                    "qq_id": bound_info.get("qq_id", ""),
                    "is_target": player_name == target_name,
                    "stats": self._extract_player_data(player_raw, player_name),
                }
            )

        teammate_names = [
            player["name"] for player in bound_team_players if not player["is_target"]
        ]
        if not teammate_names:
            return default_result

        worst_player = min(
            bound_team_players,
            key=lambda player: self._worst_player_key(player["stats"]),
        )
        target_is_worst = bool(worst_player["is_target"])
        worst_player_qq = None if target_is_worst else worst_player["qq_id"]
        return {
            "teammate_names": teammate_names,
            "worst_player_qq": worst_player_qq,
            "worst_player_name": worst_player["name"],
            "target_is_worst": target_is_worst,
        }

    @staticmethod
    def _resolve_groups_by_player_name(group_1, group_2, player_name):
        for candidate in group_1:
            username = (
                candidate.get("user_info", {}).get("user_data", {}).get("username", "")
            )
            if username == player_name:
                return group_1, group_2
        for candidate in group_2:
            username = (
                candidate.get("user_info", {}).get("user_data", {}).get("username", "")
            )
            if username == player_name:
                return group_2, group_1
        return None, None

    @staticmethod
    def _worst_player_key(player_stats: PlayerStats) -> tuple:
        return (
            player_stats.rating,
            player_stats.adr,
            player_stats.kill - player_stats.death,
            player_stats.kill,
        )

    @staticmethod
    def _extract_player_data(json_data, player) -> PlayerStats:
        kill = int(json_data.get("fight", {}).get("kill", 0))
        return PlayerStats(
            playername=player,
            uuid=json_data.get("user_info", {}).get("user_data", {}).get("uuid", ""),
            uid=json_data.get("user_info", {}).get("user_data", {}).get("uid", ""),
            win=int(json_data.get("fight", {}).get("is_win", 0)),
            elo_change=float(json_data.get("sts", {}).get("change_elo", 0)),
            rating=float(json_data.get("fight", {}).get("rating2", 0.0)),
            adr=float(json_data.get("fight", {}).get("adr", 0.0)),
            rws=float(json_data.get("fight", {}).get("rws", 0.0)),
            kill=kill,
            death=int(json_data.get("fight", {}).get("death", 0)),
            headshot_rate=(
                0
                if kill == 0
                else int(json_data.get("fight", {}).get("headshot", 1)) / kill
            ),
        )
