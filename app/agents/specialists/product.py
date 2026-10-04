from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import Agent, RunContext, Tool
from app.db import repositories as repo
from app.db.models import Product

INSTRUCTIONS = """You are the product specialist of an online store.
Use your tools to answer questions about products: details, price and availability.
- When searching, use 1-3 short keywords (e.g. "running shoes"); retry with fewer words if nothing is found.
- Only recommend products returned by tools; never invent products, prices or stock.
Reply with a short, factual summary."""


class SearchProductsArgs(BaseModel):
    query: str = Field(min_length=1, max_length=100, description="1-3 keywords, e.g. 'wireless earbuds'")


class GetProductArgs(BaseModel):
    sku: str = Field(description="Product SKU, e.g. AUD-1001")


def _serialize(product: Product) -> dict:
    return {
        "sku": product.sku,
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "in_stock": product.stock > 0,
        "units_available": product.stock,
    }


async def search_products(ctx: RunContext, args: SearchProductsArgs) -> dict:
    products = await repo.search_products(ctx.session, args.query)
    return {"products": [_serialize(p) for p in products]}


async def get_product(ctx: RunContext, args: GetProductArgs) -> dict:
    product = await repo.get_product_by_sku(ctx.session, args.sku)
    if product is None:
        return {"found": False, "message": "No product with that SKU."}
    return {"found": True, **_serialize(product)}


def build_product_agent() -> Agent:
    return Agent(
        name="product_agent",
        description=(
            "Product specialist: searches the catalog and answers questions about product "
            "details, price and stock availability."
        ),
        instructions=INSTRUCTIONS,
        tools=(
            Tool("search_products", "Search the catalog by keywords.",
                 SearchProductsArgs, search_products),
            Tool("get_product", "Get one product by SKU.", GetProductArgs, get_product),
        ),
    )
