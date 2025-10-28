import re
import json
import aiohttp
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api.message_components import Face, Plain, At
# from astrbot.core.provider import Provider

from .core.plugin_logic import CstatsCheckPluginLogic

#todo: 增加错误处理和日志记录
#todo: 优化数据存储结构，支持多个玩家数据，解决self数据的覆盖问题
#todo：增加战绩数据的格式化输出，而不是仅仅输出地图名称
#todo：增加命令帮助信息，方便用户使用

@register("cstatcheck", "badbirdy", "一个简单的 cs 战绩查询插件", "1.0.0")
class Cstatscheck(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir()
        self.user_data_file = self.data_dir / "user_data.json"
        self._session = None
        self.plugin_logic = CstatsCheckPluginLogic(self._session, prompt="")

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        #  确保数据目录存在
        self.data_dir.mkdir(exist_ok=True)
        # 如果用户数据文件不存在，则创建一个空的 JSON 文件
        if not self.user_data_file.exists():
            with open(self.user_data_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
        self._session = aiohttp.ClientSession()
    @filter.command("bind", alias={'绑定', '添加用户', '用户', '添加玩家', '玩家'})
    async def add_player_data(self, event: AstrMessageEvent):
        """响应用户添加玩家请求，并进行将玩家数据进行存储"""

        request_data = await self.plugin_logic.handle_player_data_request(event, ["stat"])
        full_text = event.message_str.strip()
        match = re.match(r"^(?:添加用户|用户|添加玩家|玩家)\s*(.+)", full_text)
        if match is not None:
            request_data.playername = match.groups()[0].strip()
        # request_data.username = event.get_sender_name()
        request_data.qq_id = event.get_sender_id()
        qq_id = event.get_sender_id()
        request_data.domain = None
        request_data.uuid = None

        if await self.plugin_logic.user_is_added(self.username, request_data.playername):
            yield event.plain_result(f"用户 {self.username} 已添加玩家 {request_data.playername} 的数据。")
            return
        async with aiohttp.ClientSession() as session:
            request_data.domain = await self.plugin_logic.get_domain(session, request_data)
            if not request_data.domain:
                yield event.plain_result(f"获取玩家 {request_data.playername} 的 domain 信息失败，请稍候重试")
                return
            # else:
            #     yield event.plain_result(f"成功获取到 domain: {request_data.domain}")
            request_data.uuid = await self.plugin_logic.get_uuid(session, request_data)
            if not request_data.uuid:
                yield event.plain_result(f"获取玩家 {request_data.playername} 的 uuid 信息失败，请稍后重试")
                return
            # else:
            #     yield event.plain_result(f"成功获取到 uuid: {request_data.uuid}")

        # 存储玩家信息到 JSON 文件
        player_data = {}
        if self.user_data_file.exists():
            with open(self.user_data_file, "r", encoding="utf-8") as f:
                player_data = json.load(f)
        player_data[self.username] = {
            "qqid": qq_id,
            "name": request_data.playername,
            "domain": request_data.domain,
            "uuid": request_data.uuid,
        }
        yield event.plain_result(f"成功添加用户 {self.username} 对应的玩家 {request_data.playername} 数据。")
        with open(self.user_data_file, "w", encoding="utf-8") as f:
            json.dump(player_data, f, ensure_ascii=False, indent=4)
    
    @filter.command("match", alias={'战绩', '获取战绩'})
    async def fetch_match_stats(self, event: AstrMessageEvent):
        """响应用户获取战绩请求，读取存储的玩家数据并获取战绩信息"""
        request_data = await self.plugin_logic.handle_player_data_request(event, ["stat"])
        full_text = event.message_str.strip()
        match = re.match(r"^(?:获取战绩|战绩|match)\s*@?([^\(]+)", full_text)
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
            qqid = player_data[self.username]["qqid"]
        player_info = player_data[self.username]
        # 更新 request_data.uuid
        request_data.uuid = player_info.get("uuid")
        async with aiohttp.ClientSession() as session:
            match_id = await self.plugin_logic.get_match_id(session, request_data)
            if not match_id:
                yield event.plain_result(f"未找到玩家 {player_info.get('name')} 的最近比赛信息。")
                return
            # else:
            #     yield event.plain_result(f"玩家 {player_info.get('name')} 最近的一场比赛 ID: {match_id}")
            match_stats = await self.plugin_logic.get_match_stats(session, match_id)
            if not match_stats:
                yield event.plain_result(f"未能获取比赛 {match_id} 的详细数据。")
                return
            # else:
            #     yield event.plain_result(f"成功获取比赛 {match_id} 的详细数据。")
            with open(self.user_data_file, "r", encoding="utf-8") as f:
                player_data = json.load(f)
            # 这里其实需要获取群聊中其他玩家的名字来加载 teammate_of_send
            teammate_of_send = [pinfo["name"] for uname, pinfo in player_data.items() if uname != self.username]
            match_map, player_send_data, noobname, noobdata = await self.plugin_logic.process_json(match_stats, match_id, player_send, teammate_of_send)
            player_send_text = f"5eplayer {player_send} 最近一场比赛战绩：\nMap: {match_map}\n比赛结果: {player_send_data['is_win']}\nRating: {player_send_data['rating']} \nADR: {player_send_data['adr']}\nElo变化: {player_send_data['change_elo']}\n"
            if noobname == "":
                noob_text = "你一个人偷偷玩的，真厉害"
            elif noobname == player_send:
                noob_text = "你就是最菜的，怎么敢查战绩的"
            else:
                noob_text = f"本场菜比是 {noobname}，打出了 {noobdata['rating']} 超高rating，这是人类啊"
            final_text = player_send_text + noob_text
            # yield event.chain_result([Plain(final_text)])
            prov = self.context.get_using_provider(umo=event.unified_msg_origin)
            if prov:
                llm_resp = await prov.text_chat(
                    prompt=f"{player_info.get('name')} 的最近一场比赛中：{final_text}",
                    context=[
                        {"role": "user", "content": ""},
                        {"role": "cs战绩短评官", "content": "response balabala"}
                    ],
                    system_prompt="你需要对上面的cs战绩进行一个简短的评价，不超过二十个字，rating 和 adr 是这局表现的重要参考因素，rating 和 adr 很高(1.2raing以上或者90ADR以上，越高越强，夸得越凶)但是输了可以用悲情英雄、尽力局、拉满了、燃成灰了、一绿带四红来形容，打得好赢了可以用大哥、带飞等来形容，打得菜(0.8rating以下或者50ADR以下，越低越菜，骂得越狠)可以用美美隐身、这把睡了、摊子、fvv、玩家名称中选一部分+出(比如玩家名称叫玩机器，就可以称为 玩出) 作为称呼来形容，如果战绩一般就正常评价吧"
                )
                logger.info(llm_resp)
                yield event.chain_result([Plain(player_send_text), Plain(llm_resp.completion_text)])

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
