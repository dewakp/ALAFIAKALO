#!/usr/bin/env python3
"""Probe Firestore to find user and count subcollection records."""

import firebase_admin
from firebase_admin import credentials, firestore

SERVICE_ACCOUNT = '/Users/woleakpose/Downloads/alafia-9i0hh-firebase-adminsdk-fbsvc-fb3e9a5364.json'
TARGET_EMAIL = 'developer@hntsolutions.com'

cred = credentials.Certificate(SERVICE_ACCOUNT)
app = firebase_admin.initialize_app(cred)
db = firestore.client()

# Find user by email
print(f"Looking for user: {TARGET_EMAIL}")
users = db.collection('users').where('pi.email', '==', TARGET_EMAIL).get()
if not users:
    users = db.collection('users').where('email', '==', TARGET_EMAIL).get()

if not users:
    print("Not found by query. Listing all users...")
    all_users = db.collection('users').get()
    for u in all_users:
        data = u.to_dict()
        pi = data.get('pi', {})
        email = pi.get('email', data.get('email', '?'))
        print(f"  UID: {u.id}, Email: {email}, Name: {pi.get('firstName', '?')} {pi.get('lastName', '?')}")
    firebase_admin.delete_app(app)
    exit()

uid = users[0].id
print(f"Found user UID: {uid}")
data = users[0].to_dict()
pi = data.get('pi', {})
print(f"  Name: {pi.get('firstName', '?')} {pi.get('lastName', '?')}")
print(f"  Email: {pi.get('email', '?')}")

# Count all subcollections
subcollections = [
    'vitalsLog', 'nutritionLog', 'medicationLog', 'eliminationLog',
    'symptomLog', 'journalEntries', 'hemodialysisFlowsheets',
    'labReports', 'scheduledEvents', 'peritonealDialysisLog'
]

print(f"\nSubcollection record counts:")
for sub in subcollections:
    docs = db.collection('users').document(uid).collection(sub).get()
    count = len(docs)
    if count > 0:
        # Show date range from first/last
        dates = []
        for d in docs:
            dd = d.to_dict()
            dt = dd.get('date')
            if dt:
                dates.append(str(dt))
        dates.sort()
        date_info = f"  ({dates[0]} to {dates[-1]})" if dates else ""
        print(f"  {sub}: {count} records{date_info}")
    else:
        print(f"  {sub}: 0")

# Sample one record from each non-empty subcollection
print(f"\nSample records (first doc from each):")
for sub in subcollections:
    docs = db.collection('users').document(uid).collection(sub).limit(1).get()
    if docs:
        d = docs[0].to_dict()
        print(f"\n  === {sub} ===")
        for k, v in sorted(d.items()):
            val_str = str(v)
            if len(val_str) > 100:
                val_str = val_str[:100] + "..."
            print(f"    {k}: {val_str}")

firebase_admin.delete_app(app)
