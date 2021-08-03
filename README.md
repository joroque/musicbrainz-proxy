# musicbrainz-proxy

Code exercise for Backend Engineer.

## Design Constraints

- Simplicity over "best practices", it's an exercise.
- Everything in a single Python module and no database or persistence layer,
    for simplicity.
- No Django or full-featured frameworks. Nothing against them, it' just they're
    overkill for the exercise and we would end up with more boilerplate
    code than anything else.
- `requests` and `hug` as the only third-party libraries to handle HTTP stuff.


## Installation

### Docker (Recommended)

Assuming Docker is installed in the system, just run:

```shell
pushd musicbrainz-proxy; docker build -t musicbrainz-proxy:latest . && docker run --rm -ti -p 9999:8000 musicbrainz-proxy:latest; popd
```

The container's port `8000` is published to port `9999` on the Docker host. To access
the endpoint from your terminal run:

```bash
curl -s --request GET \
--url 'http://127.0.0.1:9999/albums/?mbid=f6beac20-5dfe-4d1f-ae02-0b0a740aafd6&offset=4&limit=37' | jq
```

**Output:**

```json
{
  "albums": [
    {
      "mbid": "5bc030ca-10f1-4d61-bfd2-846873cd9e1b",
      "name": "Goblin",
      "year": 2011,
      "release_count": 5
    },
    {
      "mbid": "c65de046-7a48-4269-b4e5-4db0ed328f47",
      "name": "CALL ME IF YOU GET LOST",
      "year": 2021,
      "release_count": 5
    },
    {
      "mbid": "27881759-88c1-48df-aa72-1ec149f1b5c9",
      "name": "Bastard",
      "year": 2009,
      "release_count": 1
    }
  ]
}
```

### pyenv + virtualenv

A vanilla installation is also available. Most Python versions >3.6 should work
but it's only been tested with 3.9.1.

```shell
$ cd musicbrainz-proxy/
$ pyenv install 3.9.1
$ pyenv virtualenv 3.9.1 musicbrainz
$ pyenv local musicbrainz
$ pip install -r requirements.txt
```


## Limitations / Known Issues

The web service is currently limited by MusicBrainz's [rates](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting).

To obtain the number of releases per release-group/album, we have to go through
all the artist's releases and put each one in its corresponding group. This seems
to be the method that makes the least amount of API calls in the majority of cases.
Other approaches require us to know the MusicBrainz IDs in advance to either:
    a) Make a request to fetch all releases for each release group. Assuming the
    releases of every release-group fit in a single page/request we'd be making
    (n + 1) API calls per artist, where n is the number of release-groups; or
    b) Make a request to fetch the release-group of each release. This is worse
    than the former.

None of the options above seems ideal. At least by fetching all releases and their
release group in batch before grouping, we can handle artists whose collection of
releases can be fetched before the request limit is hit.

It's possible that artists with massive collections call for a different approach.
An example of this is [The Beatles](https://musicbrainz.org/artist/b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d):

```bash
curl -s --request GET \
--url 'http://127.0.0.1:9999/albums/?mbid=b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d' | jq
```

**Output:**

```json
{
  "errors": {
    "503 Service Unavailable": "Sorry, we must have hit MusicBrainz's quota. Please try again in a minute after it resets."
  }
}
```