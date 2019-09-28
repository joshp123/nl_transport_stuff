import datetime
from collections import defaultdict
from functools import lru_cache

import requests
from dogpile.cache import make_region


# In-case we accidentally hammer the upstream API.
GLOBAL_HEADERS = {"User-Agent": "github.com/joshp123/nl_transport_stuff"}
API_URL = "http://v0.ovapi.nl/"

cache_region = make_region().configure(
    "dogpile.cache.memory", expiration_time=60
)

direction_to_destination = {
    "Northbound": [
        "Rotterdam Centraal",
        "Pijnacker Zuid",
        "Leidschenveen",
        "Den Haag Centraal",
    ],
    # De Akkers is an annoying edge case!
    "Southbound": ["De Akkers", "Slinge"],
    "Eastbound": [
        "Nesselande",
        "Capelsebrug",
        "Kralingse Zoom",
        "Binnenhof",
        "De Terp",
    ],
    "Westbound": ["Parkweg", "Schiedam Centrum"],
}

destination_to_direction = {}
for k, v in direction_to_destination.items():
    for i in v:
        destination_to_direction[i] = k


class OVAPI:
    @cache_region.cache_on_arguments()
    def get(self, endpoint):
        print("making call to {}".format(endpoint))
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
    def _all_lines(self):
        for direction in self.directions:
            yield from direction.lines

    @property
    def lines(self):
        lines = defaultdict(dict)
        for line in self._all_lines:
            lines[line.line_name][line.direction] = line
        return lines

    def summary(self):
        for line in self._all_lines:
            print(line.summary)

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
        line_names = set([t.line for t in self.trains])
        return [LineWithDirection(name, self) for name in line_names]

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
    def destinations_by_line(self):
        return {line: line.destinations for line in self.lines}

    @property
    def intervals_by_line(self):
        return {line: line.intervals for line in self.lines}


class LineWithDirection:
    def __init__(self, line_name, timing_point):
        self.line_name = line_name
        self.timing_point = timing_point

    def __repr__(self):
        return self.line_name

    @property
    def direction(self):
        return destination_to_direction[list(self.destinations)[0]]

    @property
    def summary(self):
        return {
            "name": self.line_name,
            "destinations": self.destinations,
            "next3": list(self.next_three_departure_times),
            "direction": self.direction,
            "intervals": self.intervals,
        }

    @property
    def human_summary(self):
        return (
            f"Line {self.line_name} {self.direction}: "
            f"{self.next_three_departure_times}, every {self.intervals} min."
        )

    @property
    def next_three_departure_times(self):
        retval = []
        for x in range(0, 3):
            try:
                retval.append(self.trains[x].minutes_until_departure)
            except IndexError:
                # No more departures, should log this I guess
                pass
        return retval

    @property
    def trains(self):
        return [
            t for t in self.timing_point.trains if t.line == self.line_name
        ]

    @property
    def destinations(self):
        return set([t.destination for t in self.trains])

    @property
    def intervals(self):
        intervals = []
        trains_to_use = sorted(
            self.trains, key=lambda t: t.target_arrival_time
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
        return Intervals(intervals)


class Intervals:
    def __init__(self, intervals):
        self.intervals = intervals
        self.minimum = min(intervals)
        self.maximum = max(intervals)

    def __repr__(self):
        if self.minimum != self.maximum:
            return f"{self.minimum}-{self.maximum}"
        else:
            return f"{self.minimum}"


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


def get_morning_commute():
    station = Station("Bdp")
    return station.lines["E"]["Southbound"].summary


def get_evening_commute():
    station = Station("Whp")
    return station.lines["E"]["Northbound"].summary


def main():
    print(get_morning_commute())
    return
    station_codes = ("Bdp", "Whp")
    for station_code in station_codes:
        station = Station(station_code)
        print(station)
        print(station.summary())
        continue
        for train in station.departures:
            print(train)

        for direction in station.directions:
            print(direction.destinations_by_line)
            print(direction.intervals_by_line)


if __name__ == "__main__":
    main()
