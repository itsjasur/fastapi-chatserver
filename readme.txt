project structure

chatserver/
│
├── main.py
├── app/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── endpoints.py
│   └── sockets/
│       ├── __init__.py
│       └── handlers.py
└── socket_instance.py




how to update indexes
firebase deploy --only firestore:indexes --token "$FIREBASE_TOKEN" --project simpassplatform