"""
Authentication tests for DealHunt backend.
Tests user signup, login, profile management, and anti-abuse features.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

pytestmark = pytest.mark.auth


class TestUserAuthentication:
    """Test user authentication flows."""

    def test_health_check(self, client: TestClient) -> None:
        """Test that health endpoint returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_signup_validation(self, client: TestClient) -> None:
        """Test signup with invalid data returns 422."""
        response = client.post("/api/v1/auth/signup", json={})
        assert response.status_code == 422

    def test_get_current_user_unauthorized(self, client: TestClient) -> None:
        """Test accessing /me without auth returns 401."""
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401


class TestUserProfile:
    """Test user profile operations."""

    @pytest.mark.asyncio
    async def test_user_creation(self, db_session: AsyncSession) -> None:
        """Test creating a user in database."""
        user = User(
            firebase_uid="test_uid_123",
            email="test@example.com",
            phone_number="+919999999999",
            is_active=True,
            hardware_id="hw_123",
            ip_addresses=["192.168.1.1"],
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.id is not None
        assert user.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_user_hardware_id_limit(self, db_session: AsyncSession) -> None:
        """Test hardware ID tracking for anti-abuse."""
        hardware_id = "shared_hw_123"
        
        for i in range(3):
            user = User(
                firebase_uid=f"test_uid_{i}",
                email=f"test{i}@example.com",
                phone_number=f"+91999999999{i}",
                is_active=True,
                hardware_id=hardware_id,
            )
            db_session.add(user)
        
        await db_session.commit()
        
        from sqlalchemy import select, func
        result = await db_session.execute(
            select(func.count()).where(User.hardware_id == hardware_id)
        )
        count = result.scalar()
        assert count == 3
