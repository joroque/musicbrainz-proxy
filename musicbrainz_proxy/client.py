import datetime
import logging
import time
from collections import Counter
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(filename)s::%(funcName)s:%(lineno)d - %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


class MusicBrainzException(Exception):
    """Errors originated from MusicBrainz's API."""


@dataclass
class ReleaseApiResponse:
    response_data: dict

    @property
    def total_items(self):
        return self.response_data.get("release-count", 0)

    @property
    def releases(self):
        return self.response_data.get("releases", [])


@dataclass
class ReleaseGroupApiResponse:
    response_data: dict

    @property
    def mbid(self):
        return self.response_data.get("id")

    @property
    def name(self):
        return self.response_data.get("title")

    @property
    def year(self):
        isodate = self.response_data.get("first-release-date")  # e.g. '2011-05-10'
        try:
            year = datetime.date.fromisoformat(isodate).year
        except (TypeError, ValueError):
            year = None

        return year


class MusicBrainzClient:
    """MusicBrainz HTTP API wrapper."""

    BASE_API_URL = "https://musicbrainz.org/ws/2"

    def __init__(self):
        self.client = requests.Session()
        self.client.headers.update(
            {"Accept": "application/json", "User-Agent": "musicbrainz-proxy/1.0.0"}
        )

    def browse_releases(self, artist_mbid, limit=25, offset=0):
        """Make an API call to the Browse endpoint looking for an artist's releases.

        From docs:
        https://musicbrainz.org/doc/MusicBrainz_API#Browse
        > Browse requests are the only requests which support paging: any browse
        > request supports an 'offset=' argument to get more results. Browse
        > requests also support 'limit=': the default limit is 25, and you can
        > increase that up to 100.

        """
        url = (
            f"{self.BASE_API_URL}/release/"
            f"?artist={artist_mbid}&inc=release-groups&type=album"
            f"&offset={offset}&limit={limit}&fmt=json"
        )
        try:
            response = self.client.get(url, timeout=5)
            response.raise_for_status()
            response_data = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.exception("HTTP GET to %s failed!", url)
            raise MusicBrainzException from exc
        else:
            logger.info("HTTP GET to %s", url)

        return ReleaseApiResponse(response_data=response_data)

    def get_releases(self, artist_mbid):
        """Fetch all the artist's releases.

        We're leveraring the Browse endpoint which supports up to 100 results per
        page, so getting all the albums will likely require multiple requests.

        This method uses what appears to be the most sensible way to fetch the data
        necessary to perform the 'number of releases by release-group' aggregation
        with as few HTTP requests as possible, in most cases. Artists with a larger
        number of releases will take more API requests, while artist with <100
        releases will take one single request. We wait for 1s in between requests
        to make sure the rate limit isn't hit.
        """
        releases = []
        limit = 100
        offset = 0
        try:
            response = self.browse_releases(artist_mbid, limit, offset)
        except MusicBrainzException:
            logger.exception("Could not fetch all releases for %s", artist_mbid)
            raise

        releases.extend(response.releases)
        total_releases = response.total_items
        offset += limit

        for page_offset in range(offset, total_releases, limit):
            time.sleep(1)  # Do not hit the rate limit!
            try:
                response = self.browse_releases(artist_mbid, limit, page_offset)
            except MusicBrainzException:
                logger.exception("Could not fetch all releases for %s", artist_mbid)
                raise

            releases.extend(response.releases)

        return releases

    # TODO: Test this function
    def get_aggregated_releases(self, artist_mbid):
        """Group artist's releases by release group.

        Blah blah blah

        """

        releases = self.get_releases(artist_mbid)
        release_groups = []
        release_groups_by_id = {}

        for _release in releases:
            release_group = ReleaseGroupApiResponse(_release["release-group"])
            release_groups_by_id[release_group.mbid] = {
                "mbid": release_group.mbid,
                "name": release_group.name,
                "year": release_group.year,
                "release_count": 0,
            }
            release_groups.append(release_group.mbid)

        # Update the release count of each release-group. This time just iterate
        # through the distinct release groups.
        for release_group_id, count in Counter(release_groups).items():
            release_groups_by_id[release_group_id]["release_count"] = count

        sorted_release_groups = sorted(
            release_groups_by_id.values(),
            key=lambda group: group["release_count"],
            reverse=True,
        )
        return sorted_release_groups
