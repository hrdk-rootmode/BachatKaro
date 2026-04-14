import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { notificationAPI } from '../services/notificationApi';

export const fetchUnreadCount = createAsyncThunk(
  'notifications/fetchUnreadCount',
  async (_, { rejectWithValue }) => {
    const response = await notificationAPI.getUnreadCount();
    if (response.success) {
      return response.count;
    }
    return rejectWithValue(response);
  }
);

export const fetchNotifications = createAsyncThunk(
  'notifications/fetchNotifications',
  async ({ limit, offset } = { limit: 20, offset: 0 }, { rejectWithValue }) => {
    const response = await notificationAPI.getNotifications(limit, offset);
    if (response.success) {
      return response.data;
    }
    return rejectWithValue(response);
  }
);

export const markNotificationAsRead = createAsyncThunk(
  'notifications/markAsRead',
  async (notificationId, { dispatch, rejectWithValue }) => {
    const response = await notificationAPI.markAsRead(notificationId);
    if (response.success) {
      dispatch(fetchUnreadCount());
      return notificationId;
    }
    return rejectWithValue(response);
  }
);

export const markAllNotificationsAsRead = createAsyncThunk(
  'notifications/markAllAsRead',
  async (_, { dispatch, rejectWithValue }) => {
    const response = await notificationAPI.markAllAsRead();
    if (response.success) {
      dispatch(fetchUnreadCount());
      return true;
    }
    return rejectWithValue(response);
  }
);

const initialState = {
  ownerUserId: null,
  unreadCount: 0,
  notifications: [],
  loading: false,
  error: null,
};

const notificationSlice = createSlice({
  name: 'notifications',
  initialState,
  reducers: {
    resetNotifications: () => initialState,
    setNotificationOwner: (state, action) => {
      const nextOwner = action.payload || null;
      if (state.ownerUserId !== nextOwner) {
        state.ownerUserId = nextOwner;
        state.notifications = [];
        state.unreadCount = 0;
      }
    },
    setNotificationsForUser: (state, action) => {
      const { userId = null, notifications = [] } = action.payload || {};
      if (state.ownerUserId !== userId) {
        state.ownerUserId = userId;
      }
      state.notifications = Array.isArray(notifications) ? notifications : [];
      state.unreadCount = state.notifications.filter((n) => !n?.is_read).length;
      state.error = null;
    },
    setUnreadCount: (state, action) => {
      state.unreadCount = action.payload;
    },
    markNotificationReadLocal: (state, action) => {
      const notificationId = String(action.payload);
      state.notifications = state.notifications.map((n) =>
        String(n?.id) === notificationId ? { ...n, is_read: true } : n
      );
      state.unreadCount = state.notifications.filter((n) => !n?.is_read).length;
    },
    markAllNotificationsReadLocal: (state) => {
      state.notifications = state.notifications.map((n) => ({ ...n, is_read: true }));
      state.unreadCount = 0;
    },
    deleteNotificationLocal: (state, action) => {
      const notificationId = String(action.payload);
      state.notifications = state.notifications.filter((n) => String(n?.id) !== notificationId);
      state.unreadCount = state.notifications.filter((n) => !n?.is_read).length;
    },
    addNewNotification: (state, action) => {
      state.notifications.unshift(action.payload);
      state.unreadCount += 1;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchUnreadCount.fulfilled, (state, action) => {
        state.unreadCount = action.payload;
      })
      .addCase(fetchNotifications.pending, (state) => {
        state.loading = true;
      })
      .addCase(fetchNotifications.fulfilled, (state, action) => {
        state.loading = false;
        state.notifications = action.payload;
      })
      .addCase(fetchNotifications.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
      })
      .addCase('auth/logout/fulfilled', () => initialState)
      .addCase('auth/logout/rejected', () => initialState);
  },
});

export const {
  resetNotifications,
  setNotificationOwner,
  setNotificationsForUser,
  setUnreadCount,
  markNotificationReadLocal,
  markAllNotificationsReadLocal,
  deleteNotificationLocal,
  addNewNotification,
} = notificationSlice.actions;

export const selectUnreadCount = (state) => state.notifications.unreadCount;
export const selectNotifications = (state) => state.notifications.notifications;
export const selectNotificationsLoading = (state) => state.notifications.loading;

export default notificationSlice.reducer;