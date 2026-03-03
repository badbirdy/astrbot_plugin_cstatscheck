from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context

from ..models.match_data import MatchData

PROMPT_PATH = Path(__file__).parent / "prompts" / "cs_comment_prompt.txt"
_LLM_SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")


class CsAiLogic:
    async def call_llm_to_generate_evaluation(
        self, event: AstrMessageEvent, context: Context, stats_text: str
    ) -> str | None:
        prov = context.get_using_provider(umo=event.unified_msg_origin)
        if prov:
            llm_resp = await prov.text_chat(
                prompt=f"{stats_text}",
                context=[
                    {
                        "role": "user",
                        "content": "5eplayer 薛定谔的哥本哈根 最近一场比赛战绩：\nMap: 炙热沙城2 \n比赛结果: 失败 \nRating: 0.91  \nADR: 53.16 \nElo变化: 12.78",
                    },
                    {"role": "assistant", "content": "评价为这把睡了，但睡得不深"},
                    {
                        "role": "user",
                        "content": "5eplayer Mr_Bip 最近一场比赛战绩：\nMap: 炙热沙城2 \n比赛结果: 失败 \nRating: 1.59  \nADR: 121.05 \nElo变化: 27.71",
                    },
                    {"role": "assistant", "content": "评价为燃成灰了都带不动四个fw"},
                    {
                        "role": "user",
                        "content": "5eplayer 薛定谔的哥本哈根 最近一场比赛战绩: Map: 炙热沙城2 比赛结果: 胜利  Elo变化: 12.78 rating: 0.91 adr: 53.16 kill: 11    death: 10 爆头率: 27.27%",
                    },
                    {"role": "assistant", "content": "评价为躺赢局，数据比体温还低"},
                    {
                        "role": "user",
                        "content": "5eplayer 薛定谔的哥本哈根 的上上局比赛战绩: Map: 炙热沙城2 比赛结果: 胜利  Elo变化: -14.88 rating: 0.71 adr: 76.94 kill: 10    death: 15 爆头率: 50.00%",
                    },
                    {
                        "role": "assistant",
                        "content": "评价为薛定谔的哥本哈出，裤子里全是尿，没有一滴汗",
                    },
                ],
                system_prompt=_LLM_SYSTEM_PROMPT,
            )
            logger.info(llm_resp)
            completion_text = llm_resp.completion_text
            completion_text = completion_text.replace("评价为：", "评价为")
            completion_text = completion_text.replace("评价为:", "评价为")
            return completion_text
        return None

    async def handle_to_llm_text(
        self,
        match_data: MatchData,
        player_send: str | None,
        platform: str,
    ) -> str:
        player_key = player_send or ""
        player_stats = match_data.player_stats.get(player_key)
        text = ""
        if player_stats:
            if player_stats.win == 1:
                match_result = "胜利"
                elo_sign = "+"
            else:
                match_result = "失败"
                elo_sign = "-"
            match_type_text = ""
            if platform in ("pw", "mm"):
                match_type_text = f"比赛类型: {match_data.match_type or '未知'}\n"
            text = (
                f"{platform}player {player_stats.playername} 的{'上' * match_data.match_round}把比赛战绩:\n"
                f"{match_type_text}"
                f"比赛时间: {match_data.start_datetime}   比赛时长: {match_data.duration}min\n"
                f"Map: {match_data.map} 比赛结果: {match_result} \n"
                f"Elo变化: {elo_sign}{abs(player_stats.elo_change)}\n"
                f"kd: {player_stats.kill}-{player_stats.death}\n"
                f"rating: {player_stats.rating}\n"
                f"adr: {player_stats.adr}\n"
                f"爆头率: {player_stats.headshot_rate * 100:.2f}% "
            )

        if not text:
            match_data.error_msg = "生成评价战绩错误"
        return text

    async def build_llm_evaluation_input(
        self,
        match_data: MatchData,
        player_send: str | None,
        public_text: str,
    ) -> str:
        player_key = player_send or ""
        player_stats = match_data.player_stats.get(player_key)
        if not player_stats:
            return public_text

        teammate_lines = []
        for teammate in match_data.teammate_players:
            teammate_lines.append(
                f"- {teammate.playername}: rating {teammate.rating}, kd {teammate.kill}-{teammate.death}, adr {teammate.adr}"
            )

        opponent_lines = []
        for opponent in match_data.opponent_players:
            opponent_lines.append(
                f"- {opponent.playername}: rating {opponent.rating}, kd {opponent.kill}-{opponent.death}, adr {opponent.adr}"
            )

        teammate_block = "\n".join(teammate_lines) if teammate_lines else "- 无"
        opponent_block = "\n".join(opponent_lines) if opponent_lines else "- 无"

        extra_context = (
            "\n\n[仅供评价使用的对局上下文，不要原样复述]\n"
            "你需要结合以下逐人数据判断是你在拖累大哥、还是你在燃尽带队、还是对手整体太强。\n"
            "队友(不含本人)逐人数据:\n"
            f"{teammate_block}\n"
            "对手逐人数据:\n"
            f"{opponent_block}"
        )

        return public_text + extra_context
