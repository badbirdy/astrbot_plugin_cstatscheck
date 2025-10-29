from dataclasses import dataclass
from typing import Dict

from datetime import datetime

@dataclass
class PlayerStats:
    playername: str
    uuid: str
    uid: str # match的json中才有的值
    win: bool
    elo_change: float # 天梯分数变化
    rating: float
    adr: float
    rws: float
    kill: int
    death: int
    headshot_rate: float # 爆头率

@dataclass
class MatchData:
    map: str
    start_time: int # Unix 时间戳 timestamp
    end_time: int
    player_stats: Dict[str, PlayerStats]
    mvp_uid: str

    @property
    def start_datetime(self):
        """
        ts = 1761376186
        dt = datetime.fromtimestamp(ts)
        print(dt)
        2025-10-25 15:09:46
        """
        return datetime.fromtimestamp(self.start_time)

    @property
    def end_datetime(self):
        return datetime.fromtimestamp(self.end_time)

    @property
    def duration(self):
        "返回本局比赛时长(分钟)"
        return (self.end_time - self.start_time) // 60
