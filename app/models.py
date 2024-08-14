from pydantic import BaseModel


class SMSData(BaseModel):
    receiver_phone_number: str
    message: str
    title: str
    partner_code: str
    base_url: str
