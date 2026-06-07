#!/usr/bin/env python3
"""Probe ALL Firebase Auth users and their Firestore data."""

import firebase_admin
from firebase_admin import credentials, auth, firestore

SERVICE_ACCOUNT = '/Users/woleakpose/Documents/Developer/LAFIAKALO/alafia-9i0hh-firebase-adminsdk-fbsvc-fb3e9a5364.json'

cred = credentials.Certificate(SERVICE_ACCOUNT)
app = firebase_admin.initialize_app(cred)

# List ALL Firebase Auth users
print('=== FIREBASE AUTH USERS ===')
page = auth.list_users()
auth_users = []
for user in page.iterate_all():
    providers = [p.provider_id for p in user.provider_data]
    auth_users.append(user)
    print(f'  UID: {user.uid}')
    print(f'  Email: {user.email}')
    print(f'  Name: {user.display_name}')
    print(f'  Disabled: {user.disabled}')
    print(f'  Providers: {providers}')
    print(f'  Phone: {user.phone_number}')
    print(f'  Photo: {user.photo_url}')
    print(f'  Email verified: {user.email_verified}')
    print(f'  Created: {user.user_metadata.creation_timestamp}')
    print(f'  Last sign-in: {user.user_metadata.last_sign_in_timestamp}')
    print()

print(f'Total Auth users: {len(auth_users)}')

# Now check Firestore users collection
print('\n=== FIRESTORE USERS COLLECTION ===')
db = firestore.client()
fs_users = db.collection('users').get()
for u in fs_users:
    data = u.to_dict()
    pi = data.get('pi', {})
    print(f'  UID: {u.id}')
    print(f'  Email: {pi.get("email", data.get("email", "?"))}')
    name = f'{pi.get("firstName", "?")} {pi.get("lastName", "?")}'
    print(f'  Name: {name}')
    print(f'  Top-level keys: {sorted(data.keys())}')
    if isinstance(pi, dict):
        print(f'  pi keys: {sorted(pi.keys())}')
    # Show all pi values (profile info)
    if isinstance(pi, dict):
        for k, v in sorted(pi.items()):
            val = str(v)
            if len(val) > 120:
                val = val[:120] + '...'
            print(f'    pi.{k}: {val}')
    # Count subcollections
    subcols = [
        'vitalsLog', 'nutritionLog', 'medicationLog', 'eliminationLog',
        'symptomLog', 'journalEntries', 'hemodialysisFlowsheets',
        'labReports', 'scheduledEvents', 'peritonealDialysisLog',
        'fitnessLog', 'sleepLog', 'conversations', 'notifications',
        'insuranceRecords', 'mentalHealth', 'communityPosts',
    ]
    print(f'  Subcollections:')
    for sub in subcols:
        docs = db.collection('users').document(u.id).collection(sub).get()
        if len(docs) > 0:
            print(f'    {sub}: {len(docs)} records')
    print()

# Check for any top-level collections beyond 'users'
print('\n=== TOP-LEVEL COLLECTIONS ===')
for coll in db.collections():
    docs = coll.get()
    print(f'  {coll.id}: {len(docs)} documents')

firebase_admin.delete_app(app)
print('\nDone.')
