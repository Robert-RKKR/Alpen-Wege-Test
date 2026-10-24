# Third-party
from pydantic import BaseModel


class WsTicket(BaseModel):
    ticket: str
    expires_in: int
