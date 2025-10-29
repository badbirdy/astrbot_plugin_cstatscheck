import re
import json
import aiohttp
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api.message_components import Face, Plain, At
# from astrbot.core.provider import Provider

from .core.plugin_logic import CstatsCheckPluginLogic

from astrbot.core.message.components import ComponentType

#todo：增加命令帮助信息，方便用户使用

@register("cstatcheck", "badbirdy", "一个简单的 cs 战绩查询插件", "1.0.0")
class Cstatscheck(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir()
        self.user_data_file = self.data_dir / "user_data.json"
        self._session = None
        self.plugin_logic = CstatsCheckPluginLogic(self._session, self.data_dir, prompt="")

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        #  确保数据目录存在
        self.data_dir.mkdir(exist_ok=True)
        # 如果用户数据文件不存在，则创建一个空的 JSON 文件
        if not self.user_data_file.exists():
            with open(self.user_data_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
        self._session = aiohttp.ClientSession()

    @filter.command("bind", alias={'添加', '绑定', '添加用户', '用户', '添加玩家', '玩家'})
    async def add_player_data(self, event: AstrMessageEvent):
        """响应用户添加玩家请求，并进行将玩家数据进行存储"""

        request_data = await self.plugin_logic.handle_player_data_request(event, ["bind"])
        full_text = event.message_str.strip()
        match = re.match(r"^(?:添加用户|用户|添加玩家|玩家|添加|绑定|bind)\s*(.+)", full_text)
        # logger.info(f"match:{match} 和 full_text: {full_text}")
        if match is not None:
            request_data.player_name = match.groups()[0].strip()
        request_data.user_name = event.get_sender_name()
        request_data.qq_id = event.get_sender_id()
        request_data.domain = None
        request_data.uuid = None

        if request_data.player_name is None:
            logger.info("player_name 有问题")
            return 
        if await self.plugin_logic.user_is_added(request_data.user_name, request_data.player_name):
            yield event.plain_result(f"用户 {request_data.user_name} 已添加玩家 {request_data.player_name} 的数据。")
            return

        request_data.domain = await self.plugin_logic.get_domain(self._session, request_data)
        if not request_data.domain:
            yield event.plain_result(f"获取玩家 {request_data.player_name} 的 domain 信息失败，请稍候重试")
            return
        # else:
        #     yield event.plain_result(f"成功获取到 domain: {request_data.domain}")
        request_data.uuid = await self.plugin_logic.get_uuid(self._session, request_data)
        if not request_data.uuid:
            yield event.plain_result(f"获取玩家 {request_data.player_name} 的 uuid 信息失败，请稍后重试")
            return
        # else:
        #     yield event.plain_result(f"成功获取到 uuid: {request_data.uuid}")

        # 存储玩家信息到 JSON 文件
        player_data = {}
        if self.user_data_file.exists():
            with open(self.user_data_file, "r", encoding="utf-8") as f:
                player_data = json.load(f)
        player_data[request_data.qq_id] = {
            "name": request_data.player_name,
            "domain": request_data.domain,
            "uuid": request_data.uuid,
        }
        with open(self.user_data_file, "w", encoding="utf-8") as f:
            json.dump(player_data, f, ensure_ascii=False, indent=4)
        yield event.plain_result(f"成功添加用户 {request_data.user_name} 对应的玩家 {request_data.player_name} 数据。")
    
    @filter.command("match", alias={'战绩', '获取战绩'})
    async def fetch_match_stats(self, event: AstrMessageEvent):
        """响应用户获取战绩请求，读取存储的玩家数据并获取战绩信息"""
        request_data = await self.plugin_logic.handle_player_data_request(event, ["match"])
        full_text = event.message_str.strip()
        match = re.match(r"^(?:获取战绩|战绩|match)\s*@?([^\(]+)", full_text)
        qq_id = event.get_sender_id()
        if match is None:
            username = event.get_sender_name()
        else:
            username = match.groups()[0].strip()
        with open(self.user_data_file, "r", encoding="utf-8") as f:
            player_data = json.load(f)
        if qq_id not in player_data:
            yield event.plain_result(f"用户 {qq_id} 未添加数据，请先添加游戏ID")
            return
        else:
            player_send = player_data[qq_id]["name"]
        player_info = player_data[qq_id]
        # 更新 request_data.uuid
        request_data.uuid = player_info.get("uuid")
        match_id = await self.plugin_logic.get_match_id(self._session, request_data)
        if not match_id:
            yield event.plain_result(f"未找到玩家 {player_info.get('name')} 的最近比赛信息。")
            return
        # else:
        #     yield event.plain_result(f"玩家 {player_info.get('name')} 最近的一场比赛 ID: {match_id}")
        match_stats = await self.plugin_logic.get_match_stats(self._session, match_id)
        if not match_stats:
            yield event.plain_result(f"未能获取比赛 {match_id} 的详细数据。")
            return
        # else:
        #     yield event.plain_result(f"成功获取比赛 {match_id} 的详细数据。")

        # 这里其实需要获取群聊中其他玩家的名字来加载 teammate_of_send
        teammate_of_send = [pinfo["name"] for qid, pinfo in player_data.items() if qid != request_data.qq_id]
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
                    {"role": "user", "content": f"{player_send_text}"},
                    {"role": "cs战绩短评官", "content": "评价为这把睡了，但睡得不深"}
                ],
                system_prompt="你需要对上面的cs战绩进行一个简短的评价，不超过二十个字，rating 和 adr 是这局表现的重要参考因素，rating 和 adr 很高(1.2raing以上或者90ADR以上，越高越强，夸得越凶)但是输了可以用悲情英雄、尽力局、拉满了、燃成灰了、一绿带四红来形容，打得好赢了可以用大哥、带飞等来形容，打得菜(0.8rating以下或者50ADR以下，越低越菜，骂得越狠)可以用美美隐身、这把睡了、摊子、fvv、玩家名称中选一部分+出(比如玩家名称叫玩机器，就可以称为 玩出) 作为称呼来形容，如果战绩一般就正常评价吧，但是请注意，不要只是简单地采用上面的短语，要在上面的短语基础上增添内容，可以经常在句首加上“评价为”，菜的时候就刻薄一点，带点黑色幽默那种，强的时候该夸就夸，不要太夸张地夸"
            )
            logger.info(llm_resp)
            send_text = f"{player_send_text}\n{llm_resp.completion_text}"
            yield event.chain_result([Plain(send_text)])

    @filter.command("调试")
    async def testdebug(self, event: AstrMessageEvent):
        msg_chain = event.get_messages()
        for comp in msg_chain:
            if comp.type == ComponentType.At:
                com_dic = comp.toDict()
                print(com_dic)

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
