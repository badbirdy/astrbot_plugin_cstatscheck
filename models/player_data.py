from dataclasses import dataclass
from typing import Union

@dataclass
class PlayerDataRequest:
    message_str: str
    qq_id: str
    domian: str
    uuid: str
    playername: Union[str, None]
    error_msg: Union[str, None]
