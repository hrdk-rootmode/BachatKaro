"""
Notifications API Router
Handles user notifications for watchlist price drops, stock updates, and events
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import and_, desc, select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from datetime import datetime

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import Notification, User
from app.schemas import NotificationResponse

router = APIRouter()


# =============================================================================
# NOTIFICATIONS API ENDPOINTS
# =============================================================================

@router.get("/unread-count", tags=["Notifications"])
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    ✅ FIXED: Get count of unread notifications for current user
    
    Returns: { "success": true, "count": 5 }
    """
    try:
        # Count unread notifications
        stmt = select(func.count(Notification.id)).filter(
            and_(
                Notification.user_id == current_user.id,
                Notification.is_read == False
            )
        )
        result = await db.execute(stmt)
        count = result.scalar() or 0
        
        return {
            "success": True,
            "count": count
        }
    except Exception as e:
        print(f"❌ Error getting unread count: {str(e)}")
        return {"success": False, "count": 0, "error": str(e)}


@router.get("", tags=["Notifications"])
async def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    ✅ Get paginated list of notifications for current user
    Returns most recent first (newest notifications at top)
    
    Query params:
    - limit: number of notifications (1-100, default 20)
    - offset: pagination offset (default 0)
    
    Returns: { "success": true, "count": 45, "data": [...] }
    """
    try:
        # Get paginated notifications sorted by newest first
        stmt = (
            select(Notification)
            .filter(Notification.user_id == current_user.id)
            .order_by(desc(Notification.created_at))
            .limit(limit)
            .offset(offset)
        )
        
        result = await db.execute(stmt)
        notifications = result.scalars().all()
        
        return {
            "success": True,
            "count": len(notifications),
            "data": [NotificationResponse.from_orm(n) for n in notifications]
        }
    except Exception as e:
        print(f"❌ Error listing notifications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch notifications"
        )


@router.patch("/{notification_id}/read", tags=["Notifications"])
async def mark_notification_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    ✅ Mark a single notification as read
    
    Returns: { "success": true, "data": {...notification} }
    """
    try:
        # Convert string ID to UUID if needed
        try:
            notif_uuid = UUID(notification_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid notification ID format"
            )
        
        # Get notification
        stmt = select(Notification).filter(
            and_(
                Notification.id == notif_uuid,
                Notification.user_id == current_user.id
            )
        )
        result = await db.execute(stmt)
        notification = result.scalar_one_or_none()
        
        if not notification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
        
        # Update read status
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        await db.commit()
        
        return {
            "success": True,
            "data": NotificationResponse.from_orm(notification)
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error marking notification as read: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update notification"
        )


@router.patch("/mark-all-read", tags=["Notifications"])
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    ✅ Mark all notifications as read for current user
    
    Returns: { "success": true, "updated": 5 }
    """
    try:
        # Get all unread notifications
        stmt_select = select(Notification).filter(
            and_(
                Notification.user_id == current_user.id,
                Notification.is_read == False
            )
        )
        result = await db.execute(stmt_select)
        unread_notifications = result.scalars().all()
        
        # Mark all as read
        for notification in unread_notifications:
            notification.is_read = True
            notification.read_at = datetime.utcnow()
        
        await db.commit()
        
        return {
            "success": True,
            "updated": len(unread_notifications)
        }
    except Exception as e:
        print(f"❌ Error marking all as read: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update notifications"
        )


@router.delete("/{notification_id}", tags=["Notifications"])
async def delete_notification(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    ✅ Delete a notification
    
    Returns: { "success": true }
    """
    try:
        # Convert string ID to UUID if needed
        try:
            notif_uuid = UUID(notification_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid notification ID format"
            )
        
        # Delete notification
        stmt = delete(Notification).filter(
            and_(
                Notification.id == notif_uuid,
                Notification.user_id == current_user.id
            )
        )
        result = await db.execute(stmt)
        await db.commit()
        
        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
        
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error deleting notification: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete notification"
        )
