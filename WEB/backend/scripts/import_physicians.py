#!/usr/bin/env python3
"""Import physician records from Records.xlsx into ALAFIA physician directory."""
import openpyxl
import requests
import sys
from datetime import datetime

FILE = '/Users/woleakpose/Library/Mobile Documents/com~apple~CloudDocs/Records.xlsx'
API = 'http://localhost:8000/api/v1'

# Authenticate
resp = requests.post(f'{API}/auth/login', data={
    'username': 'demo@alafia.app', 'password': 'demo1234'
})
if resp.status_code != 200:
    print(f"Auth failed: {resp.text}")
    sys.exit(1)
token = resp.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

# Map raw specialties to our taxonomy
SPECIALTY_MAP = {
    'Nephrology': 'Nephrology',
    'DO': 'Internal Medicine',  # Ilse R. Levin is a DO / internist
    'Endoscopy': 'Gastroenterology',
    'Internal': 'Internal Medicine',
    'Radiology (Vascular Access)': 'Interventional Radiology',
    'Optometry': 'Ophthalmology',
    'Vascular Access': 'Vascular Surgery',
}

# Read Excel
wb = openpyxl.load_workbook(FILE, read_only=True, data_only=True)
ws = wb['Physicians']

created = 0
saved = 0
skipped = 0

for i, row in enumerate(ws.iter_rows(min_row=3, values_only=False)):  # Row 2 is sub-header
    cells = {}
    for c in row:
        try:
            cells[c.column_letter] = c.value
        except AttributeError:
            pass
    name = cells.get('B')
    if not name or not name.strip():
        continue

    name = name.strip()
    facility = (cells.get('C') or '').strip()
    raw_specialty = (cells.get('D') or '').strip()
    date_first_contact = cells.get('E')
    date_first_seen = cells.get('F')

    specialty = SPECIALTY_MAP.get(raw_specialty, raw_specialty)
    if not specialty:
        specialty = 'Internal Medicine'

    # Extract city from facility hints
    city = None
    state = 'MD'  # Most are in Maryland area
    if 'Johns Hopkins' in facility:
        city = 'Baltimore'
    elif 'Capitol Hill' in facility:
        city = 'Washington'
        state = 'DC'
    elif 'Hyattsville' in facility:
        city = 'Hyattsville'
    elif 'Kensington' in facility:
        city = 'Kensington'
    elif 'Germantown' in facility:
        city = 'Germantown'
    elif 'Gaithesburg' in facility or 'Gaithersburg' in facility:
        city = 'Gaithersburg'
    elif 'Shady Grove' in facility:
        city = 'Rockville'
    elif 'Holy Cross' in facility:
        city = 'Silver Spring'
    elif 'Rock Creek' in facility:
        city = 'Silver Spring'
    elif 'Chillum' in facility:
        city = 'Hyattsville'

    # Build credentials from raw data
    credentials = None
    if raw_specialty == 'DO':
        credentials = 'DO'
    elif 'Nephrology' in specialty or 'Internal' in specialty:
        credentials = 'MD'

    payload = {
        'full_name': name,
        'specialty': specialty,
        'facility_name': facility if facility else None,
        'city': city,
        'state_province': state,
        'country': 'US',
        'credentials': credentials,
        'accepting_new_patients': True,
    }

    # Check if already exists
    check = requests.get(f'{API}/physicians/?q={name}', headers=headers)
    existing = check.json() if check.status_code == 200 else []
    if any(p['full_name'].lower() == name.lower() for p in existing):
        print(f"  SKIP (exists): {name}")
        skipped += 1
        continue

    # Create physician
    resp = requests.post(f'{API}/physicians/', json=payload, headers=headers)
    if resp.status_code not in (200, 201):
        print(f"  FAIL creating {name}: {resp.status_code} {resp.text[:100]}")
        continue
    
    physician = resp.json()
    pid = physician['id']
    print(f"  + Created: {name} ({specialty}) at {facility} → id={pid}, geocoded={physician.get('latitude') is not None}")
    created += 1

    # Save/bookmark this physician for the user
    notes_parts = []
    if date_first_contact:
        if isinstance(date_first_contact, datetime):
            notes_parts.append(f"First contact: {date_first_contact.strftime('%Y-%m-%d')}")
    if date_first_seen:
        if isinstance(date_first_seen, datetime):
            notes_parts.append(f"First seen: {date_first_seen.strftime('%Y-%m-%d')}")

    relationship = 'Specialist'
    if specialty == 'Nephrology':
        relationship = 'Specialist'
    elif specialty == 'Internal Medicine':
        relationship = 'PCP'

    save_payload = {
        'physician_id': pid,
        'notes': '; '.join(notes_parts) if notes_parts else None,
        'relationship_type': relationship,
        'is_primary_care': (specialty == 'Internal Medicine'),
    }
    
    save_resp = requests.post(f'{API}/physicians/saved/', json=save_payload, headers=headers)
    if save_resp.status_code in (200, 201):
        saved += 1
    else:
        print(f"    (save failed: {save_resp.text[:80]})")

wb.close()

print(f"\nDone: {created} created, {saved} saved, {skipped} skipped")

# Verify
verify = requests.get(f'{API}/physicians/', headers=headers)
all_p = verify.json() if verify.status_code == 200 else []
verify_s = requests.get(f'{API}/physicians/saved/', headers=headers)
all_s = verify_s.json() if verify_s.status_code == 200 else []
print(f"Total in directory: {len(all_p)} physicians, {len(all_s)} saved")
