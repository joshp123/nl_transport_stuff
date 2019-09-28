import datetime
import json
from abc import ABCMeta

import requests

# from functools import lru_cache


class DataSource(metaclass=ABCMeta):
    def get(self):
        raise NotImplementedError


class RealDataSource(DataSource):
    endpoint = "http://v0.ovapi.nl/stopareacode/{}/departures"

    def __init__(self, stop_name, direction_code):
        self.stop_name = stop_name

    def get(self):
        url = self.endpoint.format(self.stop_name)
        return requests.get(url).json()


class FileDataSource(DataSource):
    def __init__(self, location):
        self.location = location

    # @lru_cache
    def get(self):
        with open(self.location, "r") as json_file:
            return json.load(json_file)


class Train:
    def __init__(self, train_name, train_data):
        self.train_name = train_name
        self.train_data = train_data

    def __repr__(self):
        pass

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
        return now - self.arrival_time

    @property
    def minutes_until_departure(self):
        return timedelta_to_integer_minutes(self.time_until_departure)


def timedelta_to_integer_minutes(timedelta):
    return int(timedelta.total_seeconds() / 60)


def main():
    # noqa: E501 blijdorp = FileDataSource("/Users/Josh/code/watchdepartures/blijdorp.json")
    blijdorp = RealDataSource("Bdp", "31008704")
    data = blijdorp.get()

    trains = [
        Train(k, v) for k, v in data["Bdp"]["31008703"]["Passes"].items()
    ]
    # Dict of train key name or some shit and value is JSON about train
    print(trains)
    scheduled_trains = sorted(
        trains.values(), key=lambda t: t["TargetArrivalTime"]
    )
    now = datetime.datetime.now()
    next_trains = [
        datetime.datetime.fromisoformat(t["ExpectedArrivalTime"])
        for t in trains.values()
    ]
    time_until_trains = [
        int((t - now).total_seconds() / 60) for t in next_trains
    ]
    print(sorted(time_until_trains))

    get_intervals_from_scheduled_trains(scheduled_trains)


def get_intervals_from_scheduled_trains(scheduled_trains):
    scheduled_times = [
        datetime.datetime.fromisoformat(t["TargetArrivalTime"])
        for t in scheduled_trains
    ]

    intervals = []
    for idx, time in enumerate(scheduled_times):
        try:
            interval = scheduled_times[idx + 1] - time
            interval_minutes = int(interval.total_seconds() / 60)
            intervals.append(interval_minutes)
        except IndexError:
            break
    min_interval = min(intervals)
    max_interval = max(intervals)
    if min_interval != max_interval:
        text = "{}-{}".format(min_interval, max_interval)
    else:
        text = min_interval
    interval_data = "Every {} minutes".format(text)
    print(interval_data)


if __name__ == "__main__":
    main()
