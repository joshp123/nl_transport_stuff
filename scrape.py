import datetime
from functools import lru_cache

import requests


# In-case we accidentally hammer the upstream API.
GLOBAL_HEADERS = {"User-Agent": "github.com/joshp123/nl_transport_stuff"}
API_URL = "http://v0.ovapi.nl/"


class OVAPI:
    def get(self, endpoint):
        target = "{}{}".format(API_URL, endpoint)
        resp = requests.get(target, headers=GLOBAL_HEADERS)
        resp.raise_for_status
        return resp.json()


global_api_client = OVAPI()


class Station:
    endpoint = "stopareacode/{}/departures"

    def __init__(self, stop_name):
        self.stop_name = stop_name

    def __repr__(self):
        # Kinda hacky, what if there are no timing points? w/e
        return self.directions[0].stop_name

    def _get(self):
        url = self.endpoint.format(self.stop_name)
        return global_api_client.get(url)[self.stop_name]

    @property
    # @lru_cache(maxsize=1)
    def directions(self):
        return [
            DirectionAtStation(self, timing_point)
            for timing_point in self._get().keys()
        ]

    @property
    def departures(self):
        for direction in self.directions:
            yield from direction.trains


class DirectionAtStation:
    _endpoint = "tpc/{}/departures"

    def __init__(self, station, timing_point_code):
        self.timing_point_code = timing_point_code
        self.station = station

    @property
    def endpoint(self):
        return self._endpoint.format(self.timing_point_code)

    @property
    @lru_cache(maxsize=1)
    def stop_name(self):
        return self._get()["Stop"]["TimingPointName"]

    def _get(self):
        return global_api_client.get(self.endpoint)[self.timing_point_code]

    @property
    @lru_cache(maxsize=1)
    def lines(self):
        return set([t.line for t in self.trains])

    @property
    def trains(self):
        return sorted(
            [Train(k, v) for k, v in self._get()["Passes"].items()],
            key=lambda t: t.arrival_time,
        )

    @property
    def next_arrivals(self):
        return sorted(self.trains, key=lambda t: t.arrival_time)

    @property
    def intervals(self):
        intervals_by_line = {}
        for line in self.lines:
            intervals = []
            trains_to_use = sorted(
                [t for t in self.trains if t.line == line],
                key=lambda t: t.target_arrial_time,
            )
            for idx, train in enumerate(trains_to_use):
                try:
                    interval = (
                        trains_to_use[idx + 1].target_arrival_time
                        - train.target_arrival_time
                    )
                    intervals.append(timedelta_to_integer_minutes(interval))
                except IndexError:
                    break
            intervals_by_line[line]["min"] = min(intervals)
            intervals_by_line[line]["max"] = min(intervals)


class Train:
    def __init__(self, train_name, train_data):
        self.train_name = train_name
        self.train_data = train_data

    def __repr__(self):
        return (
            f"{self.line}\t{self.destination}\t"
            f"{self.minutes_until_departure} min ({self.arrival_time.time()}, "
            f"{self.delay_mins})"
        )

    @property
    def line(self):
        return self.train_data["LinePublicNumber"]

    @property
    def destination(self):
        return self.train_data["DestinationName50"]

    @property
    def arrival_time(self):
        return datetime.datetime.fromisoformat(
            self.train_data["ExpectedArrivalTime"]
        )

    @property
    def target_arrival_time(self):
        return datetime.datetime.fromisoformat(
            self.train_data["TargetArrivalTime"]
        )

    @property
    def time_until_departure(self):
        now = datetime.datetime.now()
        return self.arrival_time - now

    @property
    def minutes_until_departure(self):
        return timedelta_to_integer_minutes(self.time_until_departure)

    @property
    def delay(self):
        return self.arrival_time - self.target_arrival_time

    @property
    def delay_mins(self):
        return self.delay.total_seconds() / 60


def timedelta_to_integer_minutes(timedelta):
    return int(timedelta.total_seconds() / 60)


def main():
    station_codes = ("Bdp", "Whp")
    for station_code in station_codes:
        station = Station(station_code)
        print(station)
        for train in station.departures:
            print(train)


if __name__ == "__main__":
    main()
