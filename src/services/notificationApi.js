import api from './api';

export const notificationAPI = {
  getUnreadCount: async () => {
    try {
      const response = await api.get('/notifications/unread-count');
      return response?.success ? response.data : { success: false, count: 0, error: response?.error };
    } catch (error) {
      console.error('Failed to fetch unread notification count:', error);
      return { success: false, count: 0 };
    }
  },

  getNotifications: async (limit = 20, offset = 0) => {
    try {
      const response = await api.get('/notifications', { limit, offset });
      return response?.success ? response.data : { success: false, data: [], error: response?.error };
    } catch (error) {
      console.error('Failed to fetch notifications:', error);
      return { success: false, data: [] };
    }
  },

  markAsRead: async (notificationId) => {
    try {
      const response = await api.put(`/notifications/${notificationId}/read`, {});
      return response?.success ? response.data : { success: false, error: response?.error };
    } catch (error) {
      console.error('Failed to mark notification as read:', error);
      return { success: false };
    }
  },

  markAllAsRead: async () => {
    try {
      const response = await api.put('/notifications/mark-all-read', {});
      return response?.success ? response.data : { success: false, error: response?.error };
    } catch (error) {
      console.error('Failed to mark all notifications as read:', error);
      return { success: false };
    }
  },

  deleteNotification: async (notificationId) => {
    try {
      const response = await api.del(`/notifications/${notificationId}`);
      return response?.success ? response.data : { success: false, error: response?.error };
    } catch (error) {
      console.error('Failed to delete notification:', error);
      return { success: false };
    }
  },
};

// Alias for convenience
export const notificationApi = notificationAPI;