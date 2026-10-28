from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session
from strawberry.fastapi import GraphQLRouter

from app.api.routes import router as api_router
from app.config import settings
from app.db import get_db, init_db
from app.graphql.schema import schema


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(api_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "crowdclean-api"}


async def get_graphql_context(db: Session = Depends(get_db)) -> dict[str, Session]:
    return {"db": db}


app.include_router(GraphQLRouter(schema, context_getter=get_graphql_context), prefix="/graphql")
