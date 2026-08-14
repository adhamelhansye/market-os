"""Agency/business access rules: agency users may access businesses they
manage; business owners access their own; unrelated tenants cannot."""

import pytest
from conftest import (
    auth_headers,
    create_business,
    create_membership,
    create_organization,
    create_role,
    create_user,
)
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def agency_world(session: AsyncSession):
    """An agency org, a client business org, and an unrelated org."""
    agency = await create_organization(session, name="Big Agency", type="agency")
    client_org = await create_organization(session, name="Client Co", type="business")
    unrelated = await create_organization(session, name="Unrelated Co", type="business")

    agency_user = await create_user(session, email="agency@example.com")
    client_user = await create_user(session, email="client@example.com")
    unrelated_user = await create_user(session, email="unrelated@example.com")

    agency_role = await create_role(
        session,
        name="owner",
        organization_id=agency.id,
        permissions=["org:read", "business:read"],
    )
    client_role = await create_role(
        session,
        name="owner",
        organization_id=client_org.id,
        permissions=["org:read", "business:read"],
    )
    unrelated_role = await create_role(
        session,
        name="owner",
        organization_id=unrelated.id,
        permissions=["org:read", "business:read"],
    )

    await create_membership(session, user=agency_user, organization=agency, role=agency_role)
    await create_membership(session, user=client_user, organization=client_org, role=client_role)
    await create_membership(
        session, user=unrelated_user, organization=unrelated, role=unrelated_role
    )
    await session.commit()

    managed_business = await create_business(
        session, organization=client_org, managed_by=agency, name="Client Store"
    )
    own_business = await create_business(session, organization=agency, name="Agency Brand")
    await session.commit()

    return {
        "agency": agency,
        "client_org": client_org,
        "unrelated": unrelated,
        "agency_user": agency_user,
        "client_user": client_user,
        "unrelated_user": unrelated_user,
        "managed_business": managed_business,
        "own_business": own_business,
    }


async def test_agency_lists_managed_and_owned_businesses(
    session: AsyncSession, client: AsyncClient, agency_world
) -> None:
    w = agency_world
    response = await client.get(
        "/api/v1/businesses",
        headers=await auth_headers(session, w["agency_user"], w["agency"].id),
    )
    assert response.status_code == 200
    names = {b["name"] for b in response.json()}
    assert names == {"Client Store", "Agency Brand"}


async def test_agency_can_read_managed_business_detail(
    session: AsyncSession, client: AsyncClient, agency_world
) -> None:
    w = agency_world
    response = await client.get(
        f"/api/v1/businesses/{w["managed_business"].id}",
        headers=await auth_headers(session, w["agency_user"], w["agency"].id),
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Client Store"


async def test_client_org_reads_own_business(
    session: AsyncSession, client: AsyncClient, agency_world
) -> None:
    w = agency_world
    response = await client.get(
        f"/api/v1/businesses/{w["managed_business"].id}",
        headers=await auth_headers(session, w["client_user"], w["client_org"].id),
    )
    assert response.status_code == 200


async def test_client_org_cannot_see_agency_other_business(
    session: AsyncSession, client: AsyncClient, agency_world
) -> None:
    w = agency_world
    response = await client.get(
        f"/api/v1/businesses/{w["own_business"].id}",
        headers=await auth_headers(session, w["client_user"], w["client_org"].id),
    )
    assert response.status_code == 404


async def test_unrelated_org_cannot_access_managed_business(
    session: AsyncSession, client: AsyncClient, agency_world
) -> None:
    w = agency_world
    response = await client.get(
        f"/api/v1/businesses/{w["managed_business"].id}",
        headers=await auth_headers(session, w["unrelated_user"], w["unrelated"].id),
    )
    assert response.status_code == 404


async def test_unrelated_org_business_list_empty(
    session: AsyncSession, client: AsyncClient, agency_world
) -> None:
    w = agency_world
    response = await client.get(
        "/api/v1/businesses",
        headers=await auth_headers(session, w["unrelated_user"], w["unrelated"].id),
    )
    assert response.status_code == 200
    assert response.json() == []