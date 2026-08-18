from src.core.exceptions import ApiError


class CollectionRequestError(ApiError):
    status_code = 422
    code = "research_collection_invalid"
