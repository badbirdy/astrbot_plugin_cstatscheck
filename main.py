import re
import shutil
import json
import aiohttp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api.message_components import Face, Plain, At
# from astrbot.core.provider import Provider

from .core.plugin_logic import CstatsCheckPluginLogic

from astrbot.core.message.components import ComponentType


@register("cstatcheck", "badbirdy", "一个简单的 cs 战绩(5e平台)查询插件", "1.0.0")
class Cstatscheck(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir()
        self.user_data_file = self.data_dir / "user_data.json"
        self._session = None
        self.plugin_logic = CstatsCheckPluginLogic(
            self._session, self.data_dir, prompt=""
        )

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        #  确保数据目录存在
        self.data_dir.mkdir(exist_ok=True)
        # 如果用户数据文件不存在，则创建一个空的 JSON 文件
        if not self.user_data_file.exists():
            with open(self.user_data_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
        self._session = aiohttp.ClientSession()

    @filter.command("bind", alias={"添加", "绑定", "添加用户", "绑定用户"})
    async def add_player_data(self, event: AstrMessageEvent):
        """响应用户添加玩家请求，并进行将玩家数据进行存储"""

        request_data = await self.plugin_logic.handle_player_data_request(
            event, ["bind", "添加", "绑定", "添加  ", "绑定用户"]
        )
        full_text = event.message_str.strip()
        match = re.match(
            r"^(?:添加用户|用户|添加玩家|玩家|添加|绑定|bind)\s*(.+)", full_text
        )
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
        if await self.plugin_logic.user_is_added(
            request_data.user_name, request_data.player_name
        ):
            yield event.plain_result(
                f"用户 {request_data.user_name} 已添加玩家 {request_data.player_name} 的数据。"
            )
            return

        request_data.domain = await self.plugin_logic.get_domain(
            self._session, request_data
        )
        if not request_data.domain:
            yield event.plain_result(
                f"获取玩家 {request_data.player_name} 的 domain 信息失败，请稍候重试"
            )
            return
        # else:
        #     yield event.plain_result(f"成功获取到 domain: {request_data.domain}")
        request_data.uuid = await self.plugin_logic.get_uuid(
            self._session, request_data
        )
        if not request_data.uuid:
            yield event.plain_result(
                f"获取玩家 {request_data.player_name} 的 uuid 信息失败，请稍后重试"
            )
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
        yield event.plain_result(
            f"成功添加用户 {request_data.user_name} 对应的玩家 {request_data.player_name} 数据。"
        )

    @filter.command("match", alias={"战绩", "获取战绩"})
    async def fetch_match_stats(self, event: AstrMessageEvent):
        """响应用户获取战绩请求，读取存储的玩家数据并获取战绩信息"""
        request_data = await self.plugin_logic.handle_player_data_request(
            event, ["match"]
        )
        msg_chain = event.get_messages()
        match_round = 1
        if len(msg_chain) == 1:
            match = re.search(r"\b(\d+)\b", msg_chain[0].toString())
            if match:
                match_round = int(match.group(1))
            request_data.qq_id = event.get_sender_id()
        else:
            for comp in msg_chain[1:]:
                if comp.type == ComponentType.At:
                    com_dic = comp.toDict()
                    request_data.qq_id = com_dic.get("data", {}).get("qq")
                if comp.type == ComponentType.Plain:
                    match = re.search(r"\b(\d+)\b", comp.toString())
                    if match:
                        match_round = int(match.group(1))
        with open(self.user_data_file, "r", encoding="utf-8") as f:
            player_data = json.load(f)
        if request_data.qq_id not in player_data:
            yield event.plain_result(f"用户 {request_data.qq_id} 未添加数据，请先添加游戏ID")
            return
        else:
            sender_playername = player_data[request_data.qq_id]["name"]
        player_info = player_data[request_data.qq_id]
        # 更新 request_data.uuid
        request_data.uuid = player_info.get("uuid")
        match_id = await self.plugin_logic.get_match_id(self._session, request_data, match_round)
        if not match_id:
            yield event.plain_result(
                f"未找到玩家 {player_info.get('name')} 的最近比赛信息。"
            )
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
        teammate_of_send = [
            pinfo["name"]
            for qid, pinfo in player_data.items()
            if qid != request_data.qq_id
        ]
        match_data = await self.plugin_logic.process_json(
            match_stats, match_round, match_id, sender_playername, teammate_of_send
        )
        stats_text = await self.plugin_logic.handle_to_llm_text(
            match_data, sender_playername
        )
        prov = self.context.get_using_provider(umo=event.unified_msg_origin)
        if prov:
            llm_resp = await prov.text_chat(
                prompt=f"{stats_text}",
                context=[
                    {"role": "user", "content": "5eplayer 薛定谔的哥本哈根 最近一场比赛战绩：\nMap: 炙热沙城2 \n比赛结果: 失败 \nRating: 0.91  \nADR: 53.16 \nElo变化: 12.78"},
                    {"role": "cs战绩短评官", "content": "评价为这把睡了，但睡得不深"},

                    {"role": "user", "content": "5eplayer Mr_Bip 最近一场比赛战绩：\nMap: 炙热沙城2 \n比赛结果: 失败 \nRating: 1.59  \nADR: 121.05 \nElo变化: 27.71"},
                    {"role": "cs战绩短评官", "content": "评价为燃成灰了都带不动四个fw"},

                    {"role": "user", "content": "5eplayer 薛定谔的哥本哈根 最近一场比赛战绩: Map: 炙热沙城2 比赛结果: 胜利  Elo变化: 12.78 rating: 0.91 adr: 53.16 kill: 11    death: 10 爆头率: 27.27%"},
                    {"role": "cs战绩短评官", "content": "评价为躺赢局，数据比体温还低"},

                    {"role": "user", "content": "5eplayer 薛定谔的哥本哈根 的上上局比赛战绩: Map: 炙热沙城2 比赛结果: 胜利  Elo变化: -14.88 rating: 0.71 adr: 76.94 kill: 10    death: 15 爆头率: 50.00%"},
                    {"role": "cs战绩短评官", "content": "评价为薛定谔的哥本哈出，裤子里全是尿，没有一滴汗"},

                ],
                system_prompt="你需要对上面的cs战绩进行一个简短的评价，不超过二十个字，rating 和 adr 是这局表现的重要参考因素，rating 和 adr 很高(1.2raing以上或者90ADR以上，越高越强，夸得越凶)但是输了可以用悲情英雄、尽力局、拉满了、燃成灰了、一绿带四红来形容，打得好赢了可以用明星哥、个人英雄主义、大哥、数值拉满了、带飞等来形容，打得菜(0.8rating以下或者50ADR以下，越低越菜，骂得越狠)可以用美美隐身、这把睡了、摊子、不像人类、尿完了、裤子里全是尿，没有一滴汗、fvv、玩家名称中选一部分+出(比如玩家名称叫玩机器，就可以称为 玩出，请注意要根据玩家名称来，不要忽视玩家名称直接套用玩出) 作为称呼来形容，如果战绩一般就正常评价吧，但是请注意，不要只是简单地采用上面的短语，要在上面的短语基础上增添内容，可以经常在句首加上“评价为”，但是不用在后面跟上冒号这类标点，菜的时候就刻薄一点，带点平常语气说出搞笑评价、黑色幽默那种，强的时候该夸就夸，不要太夸张地夸",
            )
            logger.info(llm_resp)
            send_text = f"{stats_text}\n{llm_resp.completion_text}"
            yield event.chain_result([Plain(send_text)])

    @filter.command("调试")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def testdebug(self, event: AstrMessageEvent):
        msg_chain = event.get_messages()
        for comp in msg_chain:
            if comp.type == ComponentType.At:
                com_dic = comp.toDict()
                print(com_dic)

    @filter.command("cs_help")
    async def cs_help(self, event: AstrMessageEvent):
        """显示cs插件帮助信息"""
        prefix = "/"
        # if len(self.wake_prefix) > 0:
        #     prefix = self.wake_prefix[0]

        help_msg = f"""cstatcheck插件使用帮助：
1. 账号绑定
命令: {prefix}bind [5e_player_name] 或 {prefix}绑定 [5e_player_name]
参数: 5e_player_name - 您的5e账号名
示例: {prefix}bind ExamplePlayer

2. 战绩查询
命令: {prefix}match [@群成员] 或 {prefix}战绩 [@群成员] 或 {prefix}获取战绩 [@群成员]
参数:
  @群成员 - 可选参数，艾特某个已绑定的群成员来查询他的战绩，无此参数则查询自己战绩
示例: {prefix}match @bdbd
注: 实际使用时不需要输入[]。
"""
        yield event.plain_result(help_msg)

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        logger.info("cstatscheck 插件正在卸载，开始清理后台任务...")

        # 关闭 session
        if self._session:
            await self._session.close()

        # 清理 data_dir 下的所有文件
        if self.data_dir and self.data_dir.exists():
            try:
                # 删除整个目录及其内容
                shutil.rmtree(self.data_dir)
                logger.info(f"已删除数据目录: {self.data_dir}")
            except Exception as e:
                logger.error(f"删除数据目录时出错: {e}")

        logger.info("cstatscheck 插件已卸载，所有状态已清空。")
