import asyncio

from fastapi import APIRouter
from fastapi.params import Depends
from typing import Annotated
from starlette.responses import StreamingResponse

from app.api.dependencies import get_query_service
from app.api.schemas.query_schema import QuerySchema

from app.services.query_service import QueryService

query_router = APIRouter(tags=["data agent router"])


@query_router.post("/api/query")
async  def query_handler(
        query_schema: QuerySchema,
        query_service: Annotated[QueryService, Depends(get_query_service)]
                         ):

    return StreamingResponse(
        query_service.query(query_schema.query, query_schema.session_id),
        media_type="text/event-stream")






