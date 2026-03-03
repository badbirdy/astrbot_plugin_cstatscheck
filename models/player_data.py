from dataclasses import dataclass


@dataclass
class PlayerDataRequest:
    message_str: str
    user_name: str
    qq_id: str
    platform: str
    domain: str | None
    uuid: str | None
    player_name: str | None
    error_msg: str | None
