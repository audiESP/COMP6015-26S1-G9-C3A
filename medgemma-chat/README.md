# MedGemma AI Chat — Medical Assistant Module

A plug-and-play React Native module for AI-powered medical chat using MedGemma backend.

## Tech Stack
- **React Native** + **TypeScript**
- **NativeWind** (Tailwind CSS for React Native)
- **react-i18next** (i18n: English + Chinese)
- **Python FastAPI** backend → MedGemma model

## Project Structure
```
medgemma-chat/
├── src/
│   ├── components/        # Reusable UI components
│   │   ├── ChatBubble.tsx
│   │   ├── ChatInput.tsx
│   │   ├── AttachmentMenu.tsx
│   │   └── HistorySidebar.tsx
│   ├── screens/
│   │   └── ChatScreen.tsx
│   ├── hooks/
│   │   └── useChat.ts
│   ├── services/
│   │   └── api.ts
│   ├── i18n/
│   │   ├── index.ts
│   │   └── locales/
│   │       ├── en.json
│   │       └── zh.json
│   ├── store/
│   │   └── chatStore.ts
│   └── types/
│       └── index.ts
├── backend/
│   ├── main.py            # FastAPI server
│   ├── medgemma_service.py
│   └── requirements.txt
└── README.md
```

## Quick Start

### Frontend
```bash
npm install
npx expo start
```

### Backend
```bash
cd backend
pip install -r requirements.txt
python main.py
```

## Integration
Import `ChatScreen` into your existing app:
```tsx
import { ChatScreen } from './medgemma-chat/src/screens/ChatScreen';
// Use as a screen or modal in your navigator
```
