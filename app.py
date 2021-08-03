
import concurrent.futures
import logging
from collections import Counter
from dataclasses import dataclass, field

import hug
import requests


logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s::%(funcName)s:%(lineno)d - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


class MusicBrainzException(Exception):
    """Errors originated from MusicBrainz's API."""


@dataclass
class ReleaseApiResponse:
    status_code: int
    url: str
    response_data: dict
    
    @property
    def total_items(self):
        return self.response_data.get("release-count", 0)

    @property
    def releases(self):
        return self.response_data.get("releases", [])


@dataclass
class Artist:
    # TODO: Use types here, a new dataclass for Release
    releases: list = field(default_factory=list)

    def __post_init__(self):        
        # TODO: MOve to presentation layer
        self.release_groups = {}
        for release in self.releases:
            release_group = release["release-group"]
            self.release_groups.setdefault(release_group["id"], {
                "mbid": release_group["id"],
                "name": release_group["title"],
                # TODO: "year": 
                "release_count": 0
            })
            self.release_groups[release_group["id"]]["release_count"] += 1

    @property
    def albums(self):
        """Return the artist's album sorted by number of releases descending."""
        return sorted(
            self.release_groups.values(),
            key=lambda i: i["release_count"],
            reverse=True
        )


client = requests.Session()
client.headers.update({
        "Accept": "application/json"
})

def browse_releases(artist_mbid, limit=25, offset=0):
    """Make an API call to the Browse endpoint looking for an artist's releases.

    From docs:
    https://musicbrainz.org/doc/MusicBrainz_API#Browse
    > Browse requests are the only requests which support paging: any browse
    > request supports an 'offset=' argument to get more results. Browse
    > requests also support 'limit=': the default limit is 25, and you can
    > increase that up to 100.
    
    """

    url = (
        f"https://musicbrainz.org/ws/2/release/"
        f"?artist={artist_mbid}&inc=release-groups+artist-credits"
        f"&offset={offset}&limit={limit}&fmt=json"
    )
    try:
        # Use a short timeout as these requests are made while the web service
        # is handling an incoming HTTP request. A busy web worker waiting for
        # MusicBrainz to respond when their performance is degraded could be
        # handling other (hypothetical) requests that don't need to make any
        # API calls.
        logger.info("HTTP GET to %s", url)
        response = client.get(url, timeout=3)
        response.raise_for_status()
        response_data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise MusicBrainzException from exc

    return ReleaseApiResponse(
        status_code=response.status_code,
        url=url,
        response_data=response_data
    )

def get_releases(artist_mbid):
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
    response = browse_releases(artist_mbid, limit, offset)
    
    releases.extend(response.releases)
    
    offset += limit
    total_releases = response.total_items

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        pages = [
            executor.submit(browse_releases, artist_mbid, limit, page_offset)
            for page_offset in range(offset, total_releases, limit)
        ]
        for future in concurrent.futures.as_completed(pages):
            try:
                response = future.result()
                releases.extend(response.releases)
            except Exception as exc:
                raise MusicBrainzException from exc

    return releases


@hug.local()
@hug.cli()
@hug.get(examples='mbid=65f4f0c5-ef9e-490c-aee3-909e7ae6b2ab&offset=0&limit25')
def albums(mbid: hug.types.text, limit: int = 50, offset: int = 0):
    """Fetch all the release groups for an artist.
    
    In MusicBrainz's terminology a 'release group' is what's more commonly known
    as 'album'. A 'release' is an instance of a 'release group' you can buy as
    CD or vinyl. 
    """
    releases = get_releases(mbid)
    release_groups = []
    release_groups_by_id = {}
    
    # Iterate through the whole list of release only once 
    for release_data in releases:
            release_group_id = release_data["release-group"]["id"]
            release_group_name = release_data["release-group"]["title"]
            release_groups_by_id[release_group_id] = {
                "mbid": release_group_id,
                "name": release_group_name,
                "year": None,
                "release_count": 0,
            }
            release_groups.append(release_group_id)

    # No point to continue if no release groups are collected
    if not release_groups:
        return {"albums": []}
    
    # Update the release count of each, this time just need to iterate
    # through the distinct release groups
    for release_group_id, count in Counter(release_groups).items():
        release_groups_by_id[release_group_id]["release_count"] = count

    # Sort by release count descending to then slice the list for pagination
    albums = sorted(
        release_groups_by_id.values(),
        key=lambda group: group["release_count"],
        reverse=True
    )[offset:offset + limit]

    return {"albums": albums}


if __name__ == '__main__':
    albums.interface.cli()