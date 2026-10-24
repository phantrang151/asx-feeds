import uuid

from fastapi import Request

from tools.logger import request_id_var

REQUEST_ID_HEADER = "X-Request-ID"


async def add_request_id(request: Request, call_next):
    """
    Adds a unique request ID to each incoming request.
    Calls the next middleware or route handler,
    and adds the request ID to the response headers.

    The id is also put in request_id_var for the length of the request, so every log line
    written while handling it - in any module - carries it (see tools/logger.py), and
    ask_endpoint passes it on to LangSmith. Always generated here, never taken from an incoming
    header, so a client can't inject arbitrary text into the logs.
    """
    request_id = str(uuid.uuid4())

    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers[REQUEST_ID_HEADER] = request_id

    return response
