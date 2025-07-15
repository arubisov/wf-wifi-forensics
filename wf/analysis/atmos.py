"""
Data fetchers providing metrics for the Atmospherics pane.
"""
from wf.storage.dao import DAO

def fetch_encryption_counts(
    dao: DAO,
    start_ts: int = 0,
    end_ts: int = 2**31-1,
    include_static: bool = True,
    include_mobile: bool = True
) -> list[tuple[str, int]]:
    """
    Fetch counts of observations grouped by encryption type,
    honoring the given time window and static/mobile flags.
    """
    return dao.get_encryption_counts(start_ts, end_ts, include_static, include_mobile)

def fetch_mac_counts(
    dao: DAO,
    start_ts: int = 0,
    end_ts: int = 2**31-1,
    include_static: bool = True,
    include_mobile: bool = True,
    limit: int = 50
) -> list[tuple[str, int]]:
    """
    Fetch counts of observations per MAC, ordered descending,
    honoring the given time window and static/mobile flags.
    """
    return dao.get_mac_counts(start_ts, end_ts, include_static, include_mobile, limit)

def fetch_unique_mac_count(
    dao: DAO,
    start_ts: int = 0,
    end_ts: int = 2**31-1,
    include_static: bool = True,
    include_mobile: bool = True
) -> int:
    """
    Fetch the count of unique MAC addresses for the Atmospherics pane.
    """
    return dao.get_unique_mac_count(start_ts, end_ts, include_static, include_mobile)

def fetch_unique_ssid_count(
    dao: DAO,
    start_ts: int = 0,
    end_ts: int = 2**31-1,
    include_static: bool = True,
    include_mobile: bool = True
) -> int:
    """
    Fetch the count of unique SSIDs for the Atmospherics pane.
    """
    return dao.get_unique_ssid_count(start_ts, end_ts, include_static, include_mobile)

def fetch_oui_counts(
    dao: DAO,
    start_ts: int = 0,
    end_ts: int = 2**31-1,
    include_static: bool = True,
    include_mobile: bool = True,
    limit: int = 5
) -> list[tuple[str, int]]:
    """
    Fetch counts of observations grouped by OUI manufacturer
    for the Atmospherics pane.
    """
    return dao.get_oui_counts(start_ts, end_ts, include_static, include_mobile, limit)