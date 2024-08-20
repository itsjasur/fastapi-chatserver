import firebase_admin
from firebase_admin import credentials, storage, firestore

from sensitive import FIREBASE_BUCKET

cred = credentials.Certificate("firebase_keys.json")
firebase_admin.initialize_app(cred, {"storageBucket": FIREBASE_BUCKET})


database = firestore.client()
bucket = storage.bucket()
