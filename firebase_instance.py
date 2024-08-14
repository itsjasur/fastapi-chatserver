import firebase_admin
from firebase_admin import credentials, storage, firestore

cred = credentials.Certificate("simpassplatform-firebase-adminsdk-3tgy6-8d064c59cb.json")

firebase_admin.initialize_app(cred, {"storageBucket": "simpassplatform.appspot.com"})


database = firestore.client()
bucket = storage.bucket()
