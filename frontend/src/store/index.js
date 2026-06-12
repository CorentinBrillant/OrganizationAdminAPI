import { configureStore } from '@reduxjs/toolkit'

import campaignsReducer from './campaignsSlice'

export const store = configureStore({
  reducer: {
    campaigns: campaignsReducer,
  },
})
