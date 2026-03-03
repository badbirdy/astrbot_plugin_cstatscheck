import aiohttp

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Plain, Reply
from astrbot.api.star import Context, Star, StarTools, register

from .core.plugin_logic import CstatsCheckPluginLogic


@register("cstatcheck", "badbirdy", "全平台 cs 战绩查询插件", "2.0.0")
class Cstatscheck(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir()
        self._session = None

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        #  确保数据目录存在
        self.data_dir.mkdir(exist_ok=True)
        self._session = aiohttp.ClientSession()
        # 在 session 创建后实例化 plugin_logic
        self.plugin_logic = CstatsCheckPluginLogic(
            self._session, self.data_dir, prompt=""
        )
        await self.plugin_logic.initialize_storage()

    def _quoted_chain_result(self, event: AstrMessageEvent, chain: list):
        message_id = getattr(event.message_obj, "message_id", "")
        if message_id:
            return event.chain_result([Reply(id=message_id), *chain])
        return event.chain_result(chain)

    @filter.command("bind", alias={"添加", "绑定", "添加用户", "绑定用户"})
    async def add_player_data(self, event: AstrMessageEvent):
        """响应用户添加玩家请求，并进行将玩家数据进行存储"""
        if self._session is None:
            yield event.plain_result("插件会话尚未初始化，请稍后再试")
            return

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
        else:
            logger.info(
                f"成功获取到 {request_data.player_name} 的domain: {request_data.domain}"
            )

        # 获取玩家 uuid
        await self.plugin_logic.get_uuid(self._session, request_data)
        if not request_data.uuid:
            yield event.plain_result(
                f"获取玩家 {request_data.player_name} 的 uuid 信息失败，请检查用户名是否输入正确"
            )
            return
        else:
            logger.info(
                f"成功获取到 {request_data.player_name} 的uuid: {request_data.uuid}"
            )

        # 存储玩家信息到 sqlite 数据库
        await self.plugin_logic.save_player_binding(request_data)
        yield event.plain_result(
            f"成功添加用户 {request_data.user_name} 的 {request_data.platform} 平台玩家 {request_data.player_name}。"
        )

    @filter.command("match", alias={"战绩", "查询战绩"})
    async def fetch_match_stats(self, event: AstrMessageEvent):
        """响应用户获取战绩请求，读取存储的玩家数据并获取战绩信息"""
        if self._session is None:
            yield self._quoted_chain_result(
                event,
                [Plain("插件会话尚未初始化，请稍后再试")],
            )
            return
        (
            request_data,
            match_round,
        ) = await self.plugin_logic.handle_player_data_request_match(event)
        if request_data.error_msg:
            logger.error(f"{request_data.error_msg}")
            yield self._quoted_chain_result(event, [Plain(f"{request_data.error_msg}")])
            return
        match_id = await self.plugin_logic.get_match_id(
            self._session, request_data, match_round
        )
        if not match_id:
            logger.error(f"{request_data.error_msg}")
            yield self._quoted_chain_result(event, [Plain(f"{request_data.error_msg}")])
            return
        logger.info(f"查询到match_id:{match_id}")
        match_stats_json = await self.plugin_logic.get_match_stats(
            self._session, match_id, request_data
        )
        if request_data.error_msg:
            logger.error(f"{request_data.error_msg}")
            yield self._quoted_chain_result(event, [Plain(f"{request_data.error_msg}")])
            return
        else:
            logger.info(f"成功查询到match_id为{match_id}的详细数据")

        match_data = await self.plugin_logic.process_json(
            match_stats_json,
            match_round,
            request_data.player_name,
            request_data.platform,
            request_data.uuid,
        )
        if match_data.error_msg:
            logger.error(f"{match_data.error_msg}")
            yield self._quoted_chain_result(event, [Plain(f"{match_data.error_msg}")])
            return
        logger.info("成功处理比赛数据")
        stats_text = await self.plugin_logic.handle_to_llm_text(
            match_data, request_data.player_name, request_data.platform
        )
        if match_data.error_msg:
            logger.error(f"{match_data.error_msg}")
            yield self._quoted_chain_result(event, [Plain(f"{match_data.error_msg}")])
            return
        llm_input_text = await self.plugin_logic.build_llm_evaluation_input(
            match_data,
            request_data.player_name,
            stats_text,
        )
        rsp_text = await self.plugin_logic.call_llm_to_generate_evaluation(
            event, self.context, llm_input_text
        )
        send_text = f"{stats_text}\n{rsp_text}"

        premade_summary = await self.plugin_logic.get_premade_summary(
            match_stats_json,
            request_data.player_name,
            request_data.platform,
            request_data.uuid,
        )
        teammate_names = premade_summary.get("teammate_names", [])
        target_is_worst = premade_summary.get("target_is_worst", False)
        worst_player_qq = premade_summary.get("worst_player_qq")
        worst_player_name = premade_summary.get("worst_player_name", "")

        if teammate_names:
            teammate_text = " ".join(teammate_names)
            prefix_text = f"\n本局你和 {teammate_text} 一起组排，最菜的是 "
            if target_is_worst:
                send_text += f"{prefix_text}你自己！"
                yield self._quoted_chain_result(event, [Plain(send_text)])
                return

            if worst_player_qq:
                yield self._quoted_chain_result(
                    event,
                    [
                        Plain(send_text + prefix_text + f"{worst_player_name}"),
                        At(qq=worst_player_qq),
                        Plain("！"),
                    ],
                )
                return

        yield self._quoted_chain_result(event, [Plain(send_text)])

    @filter.command("cs_help")
    async def cs_help(self, event: AstrMessageEvent):
        """显示cs插件帮助信息"""
        prefix = "/"
        help_msg = f"""cstatcheck插件使用帮助：
1. 账号绑定
命令: {prefix}command [platform] [player_name]
参数:
    commmand - 必选命令，有 bind，绑定，绑定用户，添加，添加用户
    platform - 可选参数，支持 5e/pw，不填默认5e
    player_name - 必选参数，您的平台账号名
示例: {prefix}bind 5e ExamplePlayer
      {prefix}bind pw ExamplePlayer

2. 战绩查询
命令: {prefix}command [platform] [@群成员] [比赛场次]
参数:
  command - 必选命令，有 match，战绩，查询战绩
  platform - 可选参数，支持 5e/pw/mm，推荐放在命令后第一个参数，不填默认5e
  @群成员 - 可选参数，可以艾特某个已绑定的群成员来查询他的战绩，无此参数则查询自己战绩；若艾特的是bot，则按发送者本人查询
 比赛场次 - 可选参数，查的是倒数第几把，无此参数默认查询最近一把
  说明 - mm 查询复用 pw 绑定信息，请先使用 /bind pw 绑定完美账号
示例: {prefix}match 5e 2
      {prefix}match pw @某某
      {prefix}match mm @某某
注: 实际使用时不需要输入[]。
"""
        yield event.plain_result(help_msg)

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        logger.info("cstatscheck 插件正在卸载，开始清理后台任务...")
        if self._session:
            await self._session.close()
        logger.info("cstatscheck 插件已卸载，所有状态已清空。")
