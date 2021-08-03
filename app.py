import concurrent.futures
import datetime
import logging
from collections import Counter
from dataclasses import dataclass

import hug
import requests
from falcon import HTTPServiceUnavailable

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
            # Use a short timeout as these requests are made while the web service
            # is handling an incoming HTTP request. A busy web worker waiting for
            # MusicBrainz to respond when their performance is degraded could be
            # handling other (hypothetical) requests that don't need to make any
            # API calls.
            response = self.client.get(url, timeout=3)
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
        releases will take one single request.
        """
        releases = []

        # Make this first request, the total number of releases can be found there
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

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            pages = [
                executor.submit(self.browse_releases, artist_mbid, limit, page_offset)
                for page_offset in range(offset, total_releases, limit)
            ]
            for future in concurrent.futures.as_completed(pages):
                try:
                    response = future.result()
                    releases.extend(response.releases)
                except MusicBrainzException:
                    logger.exception("Could not fetch all releases for %s", artist_mbid)
                    raise

        return releases


@hug.local()
@hug.cli()
@hug.get(examples="mbid=65f4f0c5-ef9e-490c-aee3-909e7ae6b2ab&offset=0&limit25")
def albums(mbid: hug.types.text, limit: int = 50, offset: int = 0):
    """HTTP API endpoint that returns an artist's release groups.

    In MusicBrainz's terminology a 'release group' is what's more commonly known
    as 'album'. A 'release' is an instance of a 'release group' you can buy as
    CD, vinyl, etc.
    """
    # 1. Fetch all the releases
    try:
        releases = MusicBrainzClient().get_releases(mbid)
    except MusicBrainzException as exc:
        raise HTTPServiceUnavailable(
            description=(
                "Sorry, we must have hit MusicBrainz's quota. "
                "Please try again in a minute after it resets."
            )
        ) from exc

    # 2. Iterate once through the releases to group them by release-group
    release_groups_by_id = {}
    release_groups = []
    for _release in releases:
        release_group = ReleaseGroupApiResponse(_release["release-group"])
        release_groups_by_id[release_group.mbid] = {
            "mbid": release_group.mbid,
            "name": release_group.name,
            "year": release_group.year,
            "release_count": 0,
        }
        release_groups.append(release_group.mbid)

    # No point in continuing if there are no release groups
    if not release_groups:
        return {"albums": []}

    # 3. Update the release count of each release-group, this time just
    # iterating through the distinct release groups
    for release_group_id, count in Counter(release_groups).items():
        release_groups_by_id[release_group_id]["release_count"] = count

    # Sort by release count descending, to then slice the list for pagination
    release_groups = sorted(
        release_groups_by_id.values(),
        key=lambda group: group["release_count"],
        reverse=True,
    )[offset : offset + limit]
    return {"albums": release_groups}


if __name__ == "__main__":
    albums.interface.cli()
