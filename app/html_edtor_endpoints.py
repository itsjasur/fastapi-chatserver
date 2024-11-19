# app/api/endpoints.py
import datetime
from typing import Optional
from fastapi import APIRouter, Request
from fastapi import File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import uuid

from pydantic import BaseModel
from app.utils import format_date, get_user_info, to_datetime
from firebase_instance import database, bucket

# from google.cloud.firestore_v1.base_query import FieldFilter
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter


router = APIRouter()


class HtmlsModel(BaseModel):
    access_token: str
    carrier_type: Optional[str] = None
    selected_agent: Optional[str] = None
    selected_mvno: Optional[str] = None
    policy_date_month: Optional[str] = None
    per_page: int
    page_number: int


@router.post("/get-htmls")
async def get_htmls(data: HtmlsModel):

    print("get htmls endpoint called")
    try:
        get_user_info(data.access_token)  # used in production

        # base query
        query = database.collection("htmls")

        if data.carrier_type:
            query = query.where(filter=FieldFilter("carrierType", "==", data.carrier_type))
        if data.selected_agent:
            query = query.where(filter=FieldFilter("selectedAgent", "==", data.selected_agent))
        if data.selected_mvno:
            print("selectedMvno field called")
            # query = query.where(filter=FieldFilter("selectedMvnos", "array_contains_any", mvnos_to_check)) # this checks if any items given available
            query = query.where(filter=FieldFilter("selectedMvnos", "array_contains", data.selected_mvno))
        if data.policy_date_month:
            print("policyMonth filter applied")
            query = query.where(filter=FieldFilter("policyDateMonth", "==", data.policy_date_month))

        # adds ordering before pagination
        query = query.order_by("createdAt", direction=firestore.Query.DESCENDING)
        total_count = query.count().get()[0][0].value

        docs = query.limit(data.per_page).offset((data.page_number - 1) * data.per_page).get()

        # process results
        htmls = []
        num = (data.page_number - 1) * data.per_page
        for doc_ref in docs:
            num = num + 1
            html = doc_ref.to_dict()
            html.update(
                {
                    "updatedAt": format_date(html.get("updatedAt")),
                    "createdAt": format_date(html.get("createdAt")),
                    "policyDateMonth": html.get("policyDateMonth"),
                    "carrierType": html.get("carrierType"),
                    "selectedAgent": html.get("selectedAgent"),
                    "selectedMvnos": html.get("selectedMvnos"),
                    "num": num,
                }
            )
            htmls.append(html)

        return JSONResponse(content={"htmls": htmls, "total_count": total_count}, status_code=200)

    except Exception as e:
        print(e)
        return JSONResponse(content={"error": str(e)}, status_code=500)


class HtmlModel(BaseModel):
    access_token: str
    id: str | None = None
    title: str
    html_string: str
    carrier_type: str
    selected_agent: str
    policy_date_month: str
    selected_mvnos: list | None = None


@router.post("/save-html-string")
async def save_html_string(data: HtmlModel):

    try:

        # print(data.model_dump())
        has_access, user_name = check_role(data.access_token)

        if not has_access:
            return JSONResponse(content={"success": False, "message": "접근이 허용되지 않습니다!"}, status_code=200)

        if not data.html_string:
            raise HTTPException(status_code=400, detail="모든 필드가 채워지지 않았습니다!")

        html_data_ref = database.collection("htmls").document(data.id)
        html_data = html_data_ref.get().to_dict()

        new_html_content = {
            "id": html_data_ref.id,
            "title": data.title,
            "creator": user_name,
            "content": data.html_string,
            "updatedAt": datetime.datetime.now(),
            "carrierType": data.carrier_type,
            "selectedAgent": data.selected_agent,
            "policyDateMonth": data.policy_date_month,
            "selectedMvnos": data.selected_mvnos,
        }

        if html_data:
            # update current document
            # if created user and updated users are not same, returns access error
            if user_name != html_data.get("creator", None):
                return JSONResponse(content={"success": False, "message": "업데이트 권한이 부여되지 않았습니다."}, status_code=200)

            html_data_ref.update(new_html_content)
            message = "성공적으로 저장되었습니다!"

        else:
            # create new document
            new_html_content["createdAt"] = datetime.datetime.now()
            html_data_ref.set(new_html_content)
            message = "새 문서가 성공적으로 생성되었습니다."

        return JSONResponse(
            content={"message": message, "success": True, "id": html_data_ref.id},
            status_code=200,
        )

    except Exception as e:
        print(e)
        return JSONResponse(
            content={
                "message": f"저장에 실패했습니다!: {str(e)}",
                "success": False,
            },
            status_code=500,
        )


@router.post("/delete-html")
async def delete_html(request: Request):

    try:
        data = await request.json()
        access_token = data.get("accessToken")

        id = data.get("id", None)
        has_access, user_name = check_role(access_token)

        if not has_access:
            return JSONResponse(content={"success": False, "message": "접근이 허가되지 않았습니다"}, status_code=200)

        html_data_ref = database.collection("htmls").document(id)
        html_data = html_data_ref.get().to_dict()

        if user_name != html_data.get("creator", None):
            return JSONResponse(content={"success": False, "message": "삭제 권한이 부여되지 않았습니다."}, status_code=200)

        doc_ref = database.collection("htmls").document(id)
        doc_ref.delete()

        return JSONResponse(content={"success": True, "message": "내용이 삭제되었습니다"}, status_code=200)

    except Exception as e:
        return JSONResponse(
            content={
                "message": f"문서 삭제에 실패했습니다: {str(e)}",
                "success": False,
            },
            status_code=500,
        )


@router.post("/upload-html-image")
async def upload_html_image(file: UploadFile = File(..., max_size=1024 * 1024 * 10)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="File has no filename")
    try:
        # generates a unique filename
        filename = f"{uuid.uuid4()}.{file.filename.split('.')[-1]}"

        # creates a blob in the bucket and upload the file data
        blob = bucket.blob("html_images/" + filename)

        # reads the file content
        content = await file.read()

        # uploads the file to Firebase Storage
        blob.upload_from_string(content, content_type=file.content_type)

        # makes the blob publicly accessible (optional)
        blob.make_public()

        return JSONResponse(content={"filename": filename, "path": blob.public_url}, status_code=200)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.post("/get-html")
async def get_html(request: Request):
    data = await request.json()
    id = data.get("id", None)
    # print(id)

    try:
        doc_ref = database.collection("htmls").document(id).get()

        if doc_ref:
            html = doc_ref.to_dict()
            # html["updatedAt"] = html["updatedAt"].strftime("%Y-%m-%d %H:%M")
            html["updatedAt"] = format_date(html.get("updatedAt"))
            # html["createdAt"] = html["createdAt"].strftime("%Y-%m-%d %H:%M")
            html["createdAt"] = format_date(html.get("createdAt"))
            html["policyDateMonth"] = html.get("policyDateMonth")
            return JSONResponse(content={"html": html}, status_code=200)

        else:
            return JSONResponse(content={"html": None, "message": "Content not found"}, status_code=400)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


def check_role(access_token: str):
    try:
        user_info = get_user_info(access_token)
        user_name = user_info.get("username", None)

        roles = user_info.get("roles", [])
        required_roles = ["ROLE_SUPER", "ROLE_ADMIN", "ROLE_MANAGER", "ROLE_OPEN_ADMIN", "ROLE_OPEN_MANAGER", "ROLE_AGENCY_ADMIN"]
        has_access = any(item in roles for item in required_roles)
        return has_access, user_name

    except:
        return False, None
