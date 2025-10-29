from dataclasses import dataclass
from typing import Union

@dataclass
class PlayerDataRequest:
    message_str: str
    user_name: str
    qq_id: str
    domain: Union[str, None]
    uuid: Union[str, None]
    player_name: Union[str, None]
    error_msg: Union[str, None]
