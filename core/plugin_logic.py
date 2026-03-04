import re
from collections import defaultdict
from pathlib import Path
from time import time

import aiohttp
import aiosqlite

from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.components import ComponentType

from ..models.match_data import MatchData
from ..models.player_data import PlayerDataRequest
from .ai_logic import CsAiLogic
from .platforms import (
    FiveEPlatformLogic,
    MatchMakingPlatformLogic,
    PerfectWorldPlatformLogic,
)

PLATFORM_ALIASES = {
    "5e": "5e",
    "fivee": "5e",
    "pw": "pw",
    "wanmei": "pw",
    "perfectworld": "pw",
    "mm": "mm",
    "official": "mm",
}


class CsstatsPluginLogic:
    def __init__(self, session, data_dir, prompt: str):
        self.data_dir = data_dir
        self.user_data_file = self.data_dir / "user_data.json"
        self.user_data_db_file = self.data_dir / "user_data.db"
        self._session = session
        self.prompt = prompt
        self.ai_logic = CsAiLogic()
        self.platform_logics = {
            "5e": FiveEPlatformLogic(),
            "pw": PerfectWorldPlatformLogic(),
            "mm": MatchMakingPlatformLogic(),
        }

    async def initialize_storage(self) -> None:
        async with aiosqlite.connect(self.user_data_db_file) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_bindings (
                    qq_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    player_name TEXT NOT NULL,
                    domain TEXT,
                    uuid TEXT,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (qq_id, platform)
                )
                """
            )
            await db.commit()

        await self._migrate_json_if_needed()

    async def _migrate_json_if_needed(self) -> None:
        if not self.user_data_file.exists():
            return

        async with aiosqlite.connect(self.user_data_db_file) as db:
            cursor = await db.execute("SELECT COUNT(1) FROM user_bindings")
            row = await cursor.fetchone()
            await cursor.close()
            if row and row[0] > 0:
                return

        try:
            import json

            with open(self.user_data_file, encoding="utf-8") as file:
                legacy_data = json.load(file)
        except Exception:
            return

        now_ts = int(time())
        rows_to_insert: list[tuple[str, str, str, str, str, int]] = []

        for qq_id, user_entry in legacy_data.items():
            qq_id_str = str(qq_id)
            platform_data = user_entry.get("platform_data", {})
            for platform, bind in platform_data.items():
                normalized_platform = self.normalize_platform(platform)
                if not normalized_platform:
                    continue
                player_name = str(bind.get("name") or "").strip()
                if not player_name:
                    continue
                rows_to_insert.append(
                    (
                        qq_id_str,
                        normalized_platform,
                        player_name,
                        str(bind.get("domain") or ""),
                        str(bind.get("uuid") or ""),
                        now_ts,
                    )
                )

            legacy_platform = self.normalize_platform(user_entry.get("platform") or "")
            legacy_name = str(user_entry.get("name") or "").strip()
            if legacy_platform and legacy_name:
                rows_to_insert.append(
                    (
                        qq_id_str,
                        legacy_platform,
                        legacy_name,
                        str(user_entry.get("domain") or ""),
                        str(user_entry.get("uuid") or ""),
                        now_ts,
                    )
                )

        if not rows_to_insert:
            return

        async with aiosqlite.connect(self.user_data_db_file) as db:
            await db.executemany(
                """
                INSERT INTO user_bindings (qq_id, platform, player_name, domain, uuid, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(qq_id, platform)
                DO UPDATE SET
                    player_name=excluded.player_name,
                    domain=excluded.domain,
                    uuid=excluded.uuid,
                    updated_at=excluded.updated_at
                """,
                rows_to_insert,
            )
            await db.commit()

    def normalize_platform(self, platform: str | None) -> str | None:
        if not platform:
            return None
        return PLATFORM_ALIASES.get(platform.strip().lower())

    def extract_platform_from_message(self, message: str) -> str | None:
        tokens = [token for token in re.split(r"\s+", (message or "").strip()) if token]
        if not tokens:
            return None
        return self.normalize_platform(tokens[-1])

    async def _load_user_data(self) -> dict:
        if not Path(self.user_data_db_file).exists():
            return {}

        async with aiosqlite.connect(self.user_data_db_file) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT qq_id, platform, player_name, domain, uuid, updated_at
                FROM user_bindings
                ORDER BY updated_at DESC
                """
            )
            rows = await cursor.fetchall()
            await cursor.close()

        if not rows:
            return {}

        platform_map: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
        latest_map: dict[str, dict[str, str]] = {}

        for row in rows:
            qq_id = str(row["qq_id"])
            platform = str(row["platform"])
            bind_data = {
                "name": str(row["player_name"] or ""),
                "domain": str(row["domain"] or ""),
                "uuid": str(row["uuid"] or ""),
            }
            platform_map[qq_id][platform] = bind_data
            if qq_id not in latest_map:
                latest_map[qq_id] = {"platform": platform, **bind_data}

        user_data = {}
        for qq_id, pdata in platform_map.items():
            latest = latest_map.get(qq_id, {})
            user_data[qq_id] = {
                "platform_data": pdata,
                "platform": latest.get("platform", "5e"),
                "name": latest.get("name", ""),
                "domain": latest.get("domain", ""),
                "uuid": latest.get("uuid", ""),
            }
        return user_data

    def _resolve_default_platform(self, user_entry: dict | None) -> str:
        if not user_entry:
            return "5e"

        legacy_platform = self.normalize_platform(user_entry.get("platform"))
        if legacy_platform:
            return legacy_platform

        platform_data = user_entry.get("platform_data", {})
        if "5e" in platform_data:
            return "5e"
        if "mm" in platform_data:
            return "mm"
        if "pw" in platform_data:
            return "pw"

        return "5e"

    async def handle_player_data_request_bind(
        self,
        event: AstrMessageEvent,
    ) -> PlayerDataRequest:
        message_str = event.message_str
        qq_id = event.get_sender_id()
        username = event.get_sender_name()

        full_text = (event.message_str or "").strip()
        match = re.match(r"^(?:添加用户|绑定用户|添加|绑定|bind)\s*(.+)", full_text)
        playername = None
        platform = None
        if match is not None:
            tail = match.groups()[0].strip()
            tokens = [token for token in re.split(r"\s+", tail) if token]
            if tokens and self.normalize_platform(tokens[0]):
                platform = self.normalize_platform(tokens[0])
                tokens = tokens[1:]
            elif tokens and self.normalize_platform(tokens[-1]):
                platform = self.normalize_platform(tokens[-1])
                tokens = tokens[:-1]
            if tokens:
                playername = " ".join(tokens)

        if platform == "mm":
            error_msg = "绑定请使用 pw 进行绑定；查询官匹请使用 /match mm"
            return PlayerDataRequest(
                message_str=message_str,
                user_name=username,
                qq_id=qq_id,
                platform="pw",
                domain=None,
                uuid=None,
                player_name=playername,
                error_msg=error_msg,
            )

        user_data = await self._load_user_data()
        if platform is None:
            platform = self._resolve_default_platform(user_data.get(qq_id))

        error_msg = None
        if playername is None:
            error_msg = "玩家名称未成功识别，请检查命令输入"
        else:
            error_msg = await self._user_is_added(qq_id, playername, platform)

        return PlayerDataRequest(
            message_str=message_str,
            user_name=username,
            qq_id=qq_id,
            platform=platform,
            domain=None,
            uuid=None,
            player_name=playername,
            error_msg=error_msg,
        )

    async def handle_player_data_request_match(
        self,
        event: AstrMessageEvent,
    ) -> tuple[PlayerDataRequest, int]:
        message_str = event.message_str
        sender_id = event.get_sender_id()
        qq_id = sender_id
        self_id = str(event.get_self_id())
        username = event.get_sender_name()
        playername = None
        uuid = None
        domain = None
        error_msg = None
        platform = None

        match_round = 1
        mentioned_qq_id = ""
        mentioned_bot = False

        full_text = (event.message_str or "").strip()
        cmd_match = re.match(r"^(?:match|战绩|查询战绩)\s*(.*)$", full_text)
        if cmd_match is not None:
            tail_tokens = [
                token for token in re.split(r"\s+", cmd_match.group(1).strip()) if token
            ]
            if tail_tokens and self.normalize_platform(tail_tokens[0]):
                platform = self.normalize_platform(tail_tokens[0])
            elif tail_tokens and self.normalize_platform(tail_tokens[-1]):
                platform = self.normalize_platform(tail_tokens[-1])

        msg_chain = event.get_messages()
        for comp in msg_chain:
            if comp.type == ComponentType.At:
                comp_dict = comp.toDict()
                at_data = comp_dict.get("data", {})
                current_qq_id = str(at_data.get("qq") or at_data.get("id") or "")
                if not current_qq_id:
                    continue
                if current_qq_id == self_id:
                    mentioned_bot = True
                    continue
                if not mentioned_qq_id:
                    mentioned_qq_id = current_qq_id
            if comp.type == ComponentType.Plain:
                plain_text = getattr(comp, "text", "")
                match_obj = re.search(r"\b(\d+)\b", plain_text)
                if match_obj:
                    match_round = int(match_obj.group(1))

        if mentioned_bot:
            qq_id = sender_id
        elif mentioned_qq_id:
            qq_id = mentioned_qq_id

        user_data = await self._load_user_data()

        user_entry = user_data.get(qq_id)
        if not user_entry:
            error_msg = f"用户 {username} 未添加数据，请先添加游戏ID"
        else:
            if platform is None:
                platform = self._resolve_default_platform(user_entry)

            platform_data = user_entry.get("platform_data", {}).get(platform)
            if platform_data:
                playername = platform_data.get("name", "")
                uuid = platform_data.get("uuid", "")
                domain = platform_data.get("domain", "")
            elif platform == "mm":
                fallback_pw = user_entry.get("platform_data", {}).get("pw")
                if fallback_pw:
                    playername = fallback_pw.get("name", "")
                    uuid = fallback_pw.get("uuid", "")
                    domain = fallback_pw.get("domain", "")
                else:
                    legacy_platform = self.normalize_platform(
                        user_entry.get("platform") or "5e"
                    )
                    if legacy_platform == "pw":
                        playername = user_entry.get("name", "")
                        uuid = user_entry.get("uuid", "")
                        domain = user_entry.get("domain", "")
                    else:
                        error_msg = f"用户 {qq_id} 未绑定平台 pw，请先使用 /bind pw 绑定完美账号后再查询 mm"
            else:
                legacy_platform = self.normalize_platform(
                    user_entry.get("platform") or "5e"
                )
                if legacy_platform == platform:
                    playername = user_entry.get("name", "")
                    uuid = user_entry.get("uuid", "")
                    domain = user_entry.get("domain", "")
                else:
                    error_msg = f"用户 {qq_id} 未绑定平台 {platform}，请先使用 /bind 绑定该平台账号"

        if platform is None:
            platform = "5e"

        return (
            PlayerDataRequest(
                message_str=message_str,
                user_name=username,
                qq_id=qq_id,
                platform=platform,
                domain=domain,
                uuid=uuid,
                player_name=playername,
                error_msg=error_msg,
            ),
            match_round,
        )

    async def save_player_binding(self, request_data: PlayerDataRequest):
        async with aiosqlite.connect(self.user_data_db_file) as db:
            await db.execute(
                """
                INSERT INTO user_bindings (qq_id, platform, player_name, domain, uuid, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(qq_id, platform)
                DO UPDATE SET
                    player_name=excluded.player_name,
                    domain=excluded.domain,
                    uuid=excluded.uuid,
                    updated_at=excluded.updated_at
                """,
                (
                    request_data.qq_id,
                    request_data.platform,
                    request_data.player_name or "",
                    request_data.domain or "",
                    request_data.uuid or "",
                    int(time()),
                ),
            )
            await db.commit()

    def _get_platform_logic(self, platform: str):
        logic = self.platform_logics.get(platform)
        if logic is None:
            raise ValueError(f"unsupported platform: {platform}")
        return logic

    async def call_llm_to_generate_evaluation(self, event, context, stats_text):
        return await self.ai_logic.call_llm_to_generate_evaluation(
            event, context, stats_text
        )

    async def get_domain(
        self, session: aiohttp.ClientSession, request_data: PlayerDataRequest
    ):
        logic = self._get_platform_logic(request_data.platform)
        await logic.get_domain(session, request_data)

    async def get_uuid(
        self, session: aiohttp.ClientSession, request_data: PlayerDataRequest
    ):
        logic = self._get_platform_logic(request_data.platform)
        await logic.get_uuid(session, request_data)

    async def get_match_id(
        self,
        session: aiohttp.ClientSession,
        request_data: PlayerDataRequest,
        match_round: int,
    ):
        logic = self._get_platform_logic(request_data.platform)
        return await logic.get_match_id(session, request_data, match_round)

    async def get_match_stats(
        self,
        session: aiohttp.ClientSession,
        match_id,
        request_data: PlayerDataRequest,
    ):
        logic = self._get_platform_logic(request_data.platform)
        return await logic.get_match_stats(session, match_id, request_data)

    async def process_json(
        self,
        json_data,
        match_round: int,
        player_send,
        platform: str,
        player_uuid: str | None = None,
    ) -> MatchData:
        logic = self._get_platform_logic(platform)
        return await logic.process_json(
            json_data, match_round, player_send, player_uuid
        )

    async def get_premade_summary(
        self,
        json_data,
        player_send: str | None,
        platform: str,
        player_uuid: str | None = None,
    ) -> dict:
        logic = self._get_platform_logic(platform)
        user_data = await self._load_user_data()
        return await logic.get_premade_summary(
            user_data, json_data, player_send, player_uuid
        )

    async def handle_to_llm_text(
        self,
        match_data: MatchData,
        player_send: str | None,
        platform: str,
    ) -> str:
        return await self.ai_logic.handle_to_llm_text(match_data, player_send, platform)

    async def build_llm_evaluation_input(
        self,
        match_data: MatchData,
        player_send: str | None,
        public_text: str,
    ) -> str:
        return await self.ai_logic.build_llm_evaluation_input(
            match_data, player_send, public_text
        )

    async def _user_is_added(
        self,
        qq_id: str,
        playername: str,
        platform: str,
    ) -> str | None:
        player_data = await self._load_user_data()
        user_entry = player_data.get(qq_id)
        if not user_entry:
            return None

        platform_entry = user_entry.get("platform_data", {}).get(platform)
        if platform_entry and platform_entry.get("name") == playername:
            return f"用户 {qq_id} 已添加平台 {platform} 玩家 {playername} 的数据。"

        legacy_platform = self.normalize_platform(user_entry.get("platform") or "5e")
        if legacy_platform == platform and user_entry.get("name") == playername:
            return f"用户 {qq_id} 已添加平台 {platform} 玩家 {playername} 的数据。"

        return None
