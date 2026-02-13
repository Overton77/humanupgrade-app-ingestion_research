from datetime import datetime, timezone, timedelta

def utc_now() -> datetime: 
    return datetime.now(timezone.utc) 

def lease_deadline(seconds: int = 60) -> datetime:
    return utc_now() + timedelta(seconds=seconds)