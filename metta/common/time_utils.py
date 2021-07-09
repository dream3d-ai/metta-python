import datetime as dt


def time_ms():
    return int(dt.datetime.utcnow().timestamp() * 1e6)


def datetime_to_ms(d: dt.datetime):
    return d.timestamp() * 1e6
