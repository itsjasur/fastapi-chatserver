import requests
from firebase_admin import messaging
from sensitive import ALI_GO_API_KEY, API_SERVER_URL
import sys


def get_user_info(access_token: str):
    print("get user info API called")
    sys.stdout.flush()

    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(API_SERVER_URL, headers=headers)
    if response.status_code != 200:
        raise ValueError(f"Authentication failed. Status code: {response.status_code}")

    data = response.json()
    info = data["data"]["info"]

    agent_codes = info.get("agent_cd", [None])
    agent_code = None
    if agent_codes is not None and len(agent_codes) > 0:
        agent_code = agent_codes[0]

    return {
        "username": info["username"],
        "roles": info.get("strRoles", []),
        "name": info["name"],
        "agent_code": agent_code,
        "is_retailer": "ROLE_AGENCY" in info.get("strRoles", []),
    }

    # return {
    #     "username": "SM00001",
    #     "roles": ["ROLE_AGENCY"],
    #     "name": "심패스",
    #     "agent_codes": ["SJ"],
    #     "is_retailer": True,
    # }


def send_notification(fcmToken, title, body, chat_room_id):
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=fcmToken,
        data={
            # "room": room,
            "chat_room_id": chat_room_id,
        },
    )

    try:
        response = messaging.send(message)
        return f"Successfully sent message: {response}"
    except Exception as e:
        return f"Error sending message: {e}"


def send_multiple_notifications(fcm_tokens, title, body, chat_room_id):
    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data={
            # "room": room,
            "chat_room_id": chat_room_id,
        },
        tokens=fcm_tokens,
    )

    try:
        response = messaging.send_multicast(message)
        return f"Successfully sent messages: {response.success_count} successful, {response.failure_count} failed"
    except Exception as e:
        return f"Error sending messages: {e}"


def send_single_sms(receiver_phone_number, title, message):
    send_url = "https://apis.aligo.in/send/"  # 요청을 던지는 URL, 현재는 문자보내기
    # API key, userid, sender, receiver, msg
    # API키, 알리고 사이트 아이디, 발신번호, 수신번호, 문자내용
    sms_data = {
        "key": ALI_GO_API_KEY,  # api key
        "userid": "simpass",  # 알리고 사이트 아이디
        "sender": "0221083121",  # 발신번호
        "receiver": receiver_phone_number,  # 수신번호 (,활용하여 1000명까지 추가 가능)
        "msg": message,  # 문자 내용
        "msg_type": "LMS",  # 메세지 타입 (SMS, LMS)
        "title": title,  # 메세지 제목 (장문에 적용)
    }

    send_response = requests.post(send_url, data=sms_data)
    print(send_response.json())
