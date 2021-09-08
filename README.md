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


## Installation (pyenv + virtualenv)

Any Python versions >3.6 should work but it's only been tested with 3.9.1.

Initialize the environment and install dependencies:

```shell
$ cd musicbrainz-proxy/
$ pyenv install 3.9.1
$ pyenv virtualenv 3.9.1 musicbrainz
$ pyenv local musicbrainz
$ pip install -r requirements.dev.txt
$ pip instsall -e .
```

This installation assumes Redis is installed and running. Set the related
environment variables if they are different than the defaults shown below:

```
$ export REDIS_HOST=127.0.0.1
$ export REDIS_PORT=6379
```

Finally, run the web and the task workers:

```
$ rq worker -u redis://$REDIS_HOST:$REDIS_PORT & hug -f musicbrainz_proxy/app.py
```

Make a test request for an artist with a huge catalog like [The Beatles](https://musicbrainz.org/artist/b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d):

```bash
curl -s --request GET \
--url 'http://127.0.0.1:8000/albums/?mbid=f6beac20-5dfe-4d1f-ae02-0b0a740aafd6&offset=4&limit=37' | jq
```

**Output:**

```json
{
  "result_url": "http://127.0.0.1:8000/albums/result/47486a44-d53d-4f9a-802d-066897eb1c05"
}

```

# Outdated


## Running with Docker (outdated)

Assuming Docker is installed in the system, clone this repository and run:

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

