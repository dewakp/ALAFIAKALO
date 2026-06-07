"""
Backend launcher — loads .env via python-dotenv (avoids shell mangling of JSON values)
then starts uvicorn in-process.
"""
import os
import sys
from pathlib import Path

# This file lives in the backend directory
BACKEND_DIR = Path(__file__).resolve().parent

# Load .env BEFORE importing anything that reads settings
from dotenv import load_dotenv  # noqa: E402
load_dotenv(BACKEND_DIR / '.env', override=False)

# Make `app` package importable
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.chdir(BACKEND_DIR)

import uvicorn  # noqa: E402

if __name__ == '__main__':
    uvicorn.run(
        'app.main:app',
        host='0.0.0.0',
        port=int(os.environ.get('PORT', '8005')),
        reload=False,
    )
