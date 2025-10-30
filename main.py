import json
import aiohttp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api.message_components import Plain

from .core.plugin_logic import CstatsCheckPluginLogic

from astrbot.core.message.components import ComponentType


@register("cstatcheck", "badbirdy", "一个简单的 cs 战绩(5e平台)查询插件", "1.0.0")
class Cstatscheck(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir()
        self.user_data_file = self.data_dir / "user_data.json"
        self._session = None

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        #  确保数据目录存在
        self.data_dir.mkdir(exist_ok=True)
        # 如果用户数据文件不存在，则创建一个空的 JSON 文件
        if not self.user_data_file.exists():
            with open(self.user_data_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
        self._session = aiohttp.ClientSession()
        # 在 session 创建后实例化 plugin_logic
        self.plugin_logic = CstatsCheckPluginLogic(
            self._session, self.data_dir, prompt=""
        )

    @filter.command("bind", alias={"添加", "绑定", "添加用户", "绑定用户"})
    async def add_player_data(self, event: AstrMessageEvent):
        """响应用户添加玩家请求，并进行将玩家数据进行存储"""

        # 处理用户指令
        request_data = await self.plugin_logic.handle_player_data_request_bind(event)
        if request_data.error_msg:
            yield event.plain_result(request_data.error_msg)
            return

        # 获取玩家 domain
        await self.plugin_logic.get_domain(self._session, request_data)
        if request_data.error_msg:
            yield event.plain_result(request_data.error_msg)
            return
        # else:
        #     yield event.plain_result(f"成功获取到 domain: {request_data.domain}")

        # 获取玩家 uuid
        await self.plugin_logic.get_uuid(self._session, request_data)
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
            f"成功添加用户 {request_data.user_name} 对应玩家 {request_data.player_name} 。"
        )

    @filter.command("match", alias={"战绩", "查询战绩"})
    async def fetch_match_stats(self, event: AstrMessageEvent):
        """响应用户获取战绩请求，读取存储的玩家数据并获取战绩信息"""
        (
            request_data,
            match_round,
        ) = await self.plugin_logic.handle_player_data_request_match(event)
        match_id = await self.plugin_logic.get_match_id(
            self._session, request_data, match_round
        )
        logger.info(f"查询到match_id:{match_id}")
        if not match_id:
            yield event.plain_result(f"{request_data.error_msg}")
            return
        # else:
        #     yield event.plain_result(f"玩家 {player_info.get('name')} 最近的一场比赛 ID: {match_id}")
        match_stats_json = await self.plugin_logic.get_match_stats(
            self._session, match_id, request_data
        )
        if not match_stats_json:
            logger.info(f"未能获取比赛 {match_id} 的详细数据。")
            yield event.plain_result(
                f"获取{match_round * '上'}把比赛的详细数据失败 (match_id={match_id}) "
            )
            return
        else:
            logger.info(f"成功查询到match_id为{match_id}的详细数据")

        match_data = await self.plugin_logic.process_json(
            match_stats_json,
            match_round,
            request_data.player_name,
        )
        logger.info("成功处理比赛数据")
        stats_text = await self.plugin_logic.handle_to_llm_text(
            match_data, request_data.player_name
        )
        rsp_text = await self.plugin_logic.call_llm_to_generate_evaluation(
            event, self.context, stats_text
        )
        send_text = f"{stats_text}\n{rsp_text}"
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
        help_msg = f"""cstatcheck插件使用帮助：
1. 账号绑定
命令: {prefix}command [5e_player_name]
参数:
    commmand - 必选命令，有 bind，绑定，绑定用户，添加，添加用户
    5e_player_name - 必选参数，您的5e账号名
示例: {prefix}bind ExamplePlayer

2. 战绩查询
命令: {prefix}command [@群成员] [比赛场次]
参数:
  command - 必选命令，有 match，战绩，查询战绩
  @群成员 - 可选参数，可以艾特某个已绑定的群成员来查询他的战绩，无此参数则查询自己战绩
  比赛场次 - 可选参数，查的是倒数第几把，无此参数默认查询最近一把
示例: {prefix}match @某某 2
      {prefix}match @某某
注: 实际使用时不需要输入[]。
"""
        yield event.plain_result(help_msg)

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        logger.info("cstatscheck 插件正在卸载，开始清理后台任务...")
        if self._session:
            await self._session.close()
        logger.info("cstatscheck 插件已卸载，所有状态已清空。")
